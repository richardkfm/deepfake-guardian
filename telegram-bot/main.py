"""Telegram moderation bot entry-point.

Listens to group messages — text, captions, photos, videos, animations (GIFs),
video notes, stickers and image/video documents, including *edited* messages —
sends them to the moderation engine, and acts on the verdict.

Verdict handling (at most one group notice per moderated message):

* ``delete`` and the bot may delete → message removed, escalation notice posted
* ``delete`` but the bot may not    → admins asked to remove it
* ``flag``                          → admins asked to review it

Every non-``allow`` verdict is recorded via ``/warnings/record``; repeat
offenders escalate to admin / supervisor notices.  Admin @-mentions are
rate-limited per chat (``ADMIN_MENTION_COOLDOWN_SECONDS``).

Failure policy is **fail-open**: if the engine is unreachable the message is
left alone and an ``engine_unavailable_fail_open`` warning is logged.  Logs
carry metadata only (ids, verdicts, reasons) — never message text or media.

GDPR commands: ``/privacy``, ``/my_data`` (Art. 15, private chat only) and
``/delete_my_data`` (Art. 17).
"""
from __future__ import annotations

import html
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import structlog
from telegram import Chat, ChatMember, Message, Update, User
from telegram.constants import ChatMemberStatus, ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import engine_client
from config import settings
from i18n.loader import available_languages, get_message

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        # plain_traceback: never render local variables (they may hold message text)
        structlog.dev.ConsoleRenderer(exception_formatter=structlog.dev.plain_traceback),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logging.basicConfig(
    format="%(message)s",
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
)
# httpx logs every request URL at INFO — for the Telegram API that URL contains
# the bot token, so keep it quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_VERDICT_SEVERITY = {"allow": 0, "flag": 1, "delete": 2}
# Engine reasons that ask for human review but are not the sender's fault
# (e.g. a video the engine could not decode) — no warning is recorded.
REVIEW_ONLY_REASONS = frozenset({"unanalysable_video"})
# How long admin lists / the bot's own rights are cached per chat.
_CHAT_CACHE_TTL_SECONDS = 300.0
# Updates processed in parallel, so one slow video does not stall every group.
_MAX_CONCURRENT_UPDATES = 8

# Everything the bot moderates (commands included, so "/x <abuse>" is checked).
MODERATED_CONTENT = (
    filters.TEXT
    | filters.CAPTION
    | filters.PHOTO
    | filters.VIDEO
    | filters.ANIMATION
    | filters.VIDEO_NOTE
    | filters.Sticker.ALL
    | filters.Document.IMAGE
    | filters.Document.VIDEO
)


# ---------------------------------------------------------------------------
# Media extraction
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MediaRef:
    """A downloadable piece of media attached to a message."""

    kind: Literal["image", "video"]
    source: str  # photo / video / animation / video_note / sticker / document (for logs)
    file: Any  # PhotoSize, Video, Document, … — anything with ``get_file()``
    file_size: int | None
    thumbnail: Any | None = None  # PhotoSize fallback for oversized files


def extract_media(message: Message) -> MediaRef | None:
    """Return the moderatable media of *message*, or ``None`` if there is none."""
    if message.photo:
        photo = message.photo[-1]  # highest resolution
        return MediaRef("image", "photo", photo, photo.file_size)
    if message.video:
        v = message.video
        return MediaRef("video", "video", v, v.file_size, v.thumbnail)
    # Must precede the document branch: animations also populate ``message.document``.
    if message.animation:
        a = message.animation
        return MediaRef("video", "animation", a, a.file_size, a.thumbnail)
    if message.video_note:
        vn = message.video_note
        return MediaRef("video", "video_note", vn, vn.file_size, vn.thumbnail)
    if message.sticker:
        st = message.sticker
        if st.is_animated:
            # Lottie (.tgs) vector animation — not decodable; moderate its preview.
            if st.thumbnail is None:
                return None
            return MediaRef("image", "sticker", st.thumbnail, st.thumbnail.file_size)
        kind: Literal["image", "video"] = "video" if st.is_video else "image"
        return MediaRef(kind, "sticker", st, st.file_size, st.thumbnail)
    if message.document:
        doc = message.document
        mime = (doc.mime_type or "").lower()
        if mime.startswith("image/") and mime != "image/svg+xml":
            return MediaRef("image", "document", doc, doc.file_size, doc.thumbnail)
        if mime.startswith("video/"):
            return MediaRef("video", "document", doc, doc.file_size, doc.thumbnail)
    return None


def _select_download(media: MediaRef) -> tuple[Literal["image", "video"], Any] | None:
    """Apply the ``MAX_MEDIA_MB`` limit; fall back to the thumbnail if too large."""
    max_bytes = int(settings.max_media_mb * 1024 * 1024)
    if max_bytes <= 0 or media.file_size is None or media.file_size <= max_bytes:
        return media.kind, media.file
    if media.thumbnail is not None:
        logger.info(
            "media_too_large_using_thumbnail",
            source=media.source,
            file_size=media.file_size,
            max_bytes=max_bytes,
        )
        return "image", media.thumbnail
    logger.warning(
        "media_too_large_skipped",
        source=media.source,
        file_size=media.file_size,
        max_bytes=max_bytes,
    )
    return None


# ---------------------------------------------------------------------------
# Engine calls
# ---------------------------------------------------------------------------

def _sender_id(message: Message) -> str | None:
    """Platform ID of whoever sent *message* (a user, or a channel posting as itself)."""
    if message.sender_chat is not None:
        return str(message.sender_chat.id)
    if message.from_user is not None:
        return str(message.from_user.id)
    return None


async def _call_engine(
    content_type: str,
    func: Callable[..., Awaitable[dict[str, Any]]],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Call an engine function; on engine failure log clearly and return ``None``."""
    try:
        return await func(*args, **kwargs)
    except httpx.HTTPError as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning(
            "engine_unavailable_fail_open",
            content_type=content_type,
            error_type=type(exc).__name__,
            status=status,
            detail="message left unmoderated",
        )
        return None


def merge_results(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Combine several engine results: most severe verdict, union of reasons."""
    if not results:
        return None
    verdict = max(
        (r.get("verdict", "allow") for r in results),
        key=lambda v: _VERDICT_SEVERITY.get(v, 0),
    )
    reasons: list[str] = []
    for r in results:
        for reason in r.get("reasons") or []:
            if reason not in reasons:
                reasons.append(reason)
    language = next((r["language"] for r in results if r.get("language")), None)
    return {"verdict": verdict, "reasons": reasons, "language": language}


async def _moderate_message(message: Message) -> dict[str, Any] | None:
    """Send the text/caption and media of *message* to the engine."""
    user_id = _sender_id(message)
    group_id = str(message.chat_id)
    results: list[dict[str, Any]] = []

    text = message.text or message.caption
    if text:
        res = await _call_engine(
            "text", engine_client.moderate_text, text, user_id=user_id, group_id=group_id
        )
        if res is not None:
            results.append(res)
            if res.get("verdict") == "delete":
                # Already being removed — no need to download the media too.
                return merge_results(results)

    media = extract_media(message)
    selected = _select_download(media) if media is not None else None
    if media is not None and selected is not None:
        kind, file_obj = selected
        try:
            tg_file = await file_obj.get_file()
            data = bytes(await tg_file.download_as_bytearray())
        except TelegramError as exc:
            logger.warning(
                "media_download_failed", source=media.source, error_type=type(exc).__name__
            )
        else:
            func = engine_client.moderate_image if kind == "image" else engine_client.moderate_video
            res = await _call_engine(kind, func, data, user_id=user_id, group_id=group_id)
            if res is not None:
                results.append(res)

    return merge_results(results)


# ---------------------------------------------------------------------------
# Chat helpers (cached)
# ---------------------------------------------------------------------------
_admin_cache: dict[int, tuple[float, tuple[ChatMember, ...]]] = {}
_bot_rights_cache: dict[int, tuple[float, bool]] = {}
_last_admin_mention: dict[int, float] = {}


async def _get_admins(chat: Chat) -> tuple[ChatMember, ...]:
    now = time.monotonic()
    cached = _admin_cache.get(chat.id)
    if cached is not None and now - cached[0] < _CHAT_CACHE_TTL_SECONDS:
        return cached[1]
    try:
        admins = tuple(await chat.get_administrators())
    except TelegramError as exc:
        logger.warning("get_administrators_failed", chat_id=chat.id, error_type=type(exc).__name__)
        return ()
    _admin_cache[chat.id] = (now, admins)
    return admins


async def _bot_can_delete(message: Message, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Whether the bot is owner, or an admin holding the "Delete messages" right."""
    chat = message.chat
    if chat.type == ChatType.PRIVATE:
        return False
    now = time.monotonic()
    cached = _bot_rights_cache.get(chat.id)
    if cached is not None and now - cached[0] < _CHAT_CACHE_TTL_SECONDS:
        return cached[1]
    try:
        member = await chat.get_chat_member(context.bot.id)
    except TelegramError as exc:
        logger.warning("get_chat_member_failed", chat_id=chat.id, error_type=type(exc).__name__)
        return False
    if member.status == ChatMemberStatus.OWNER:
        can_delete = True
    elif member.status == ChatMemberStatus.ADMINISTRATOR:
        can_delete = bool(getattr(member, "can_delete_messages", False))
    else:
        can_delete = False
    _bot_rights_cache[chat.id] = (now, can_delete)
    return can_delete


def _user_mention(user: User, *, ping: bool) -> str:
    """HTML-safe mention: ``@username`` if set, else a link (``ping``) or plain name."""
    if user.username:
        return f"@{html.escape(user.username)}"
    if ping:
        return user.mention_html()
    return html.escape(user.first_name)


async def _admin_mentions(chat: Chat, *, force: bool = False) -> str:
    """Mentions of all human admins, or ``""`` while the per-chat cooldown runs."""
    now = time.monotonic()
    cooldown = settings.admin_mention_cooldown_seconds
    last = _last_admin_mention.get(chat.id)
    if not force and cooldown > 0 and last is not None and now - last < cooldown:
        logger.info("admin_mention_suppressed_cooldown", chat_id=chat.id)
        return ""
    admins = await _get_admins(chat)
    mentions = " ".join(_user_mention(a.user, ping=True) for a in admins if not a.user.is_bot)
    if mentions:
        _last_admin_mention[chat.id] = now
    return mentions


def _offender_mention(message: Message) -> str:
    if message.sender_chat is not None:
        return html.escape(message.sender_chat.title or message.sender_chat.username or "")
    if message.from_user is not None:
        return _user_mention(message.from_user, ping=False)
    return ""


# ---------------------------------------------------------------------------
# Verdict handling
# ---------------------------------------------------------------------------

async def _try_delete(message: Message, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not await _bot_can_delete(message, context):
        return False
    try:
        await message.delete()
    except TelegramError as exc:
        # e.g. message older than 48 h, or rights revoked since we cached them
        _bot_rights_cache.pop(message.chat_id, None)
        logger.warning(
            "message_delete_failed",
            chat_id=message.chat_id,
            message_id=message.message_id,
            error_type=type(exc).__name__,
        )
        return False
    logger.info("message_deleted", chat_id=message.chat_id, message_id=message.message_id)
    return True


async def _record_warning(
    message: Message, reasons: list[str]
) -> tuple[str | None, int | None]:
    """Record the violation; returns ``(escalation action, warning count)``."""
    user_id = _sender_id(message)
    if user_id is None or (reasons and set(reasons) <= REVIEW_ONLY_REASONS):
        return None, None
    try:
        res = await engine_client.record_warning(user_id, str(message.chat_id), reasons)
    except httpx.HTTPError as exc:
        logger.warning("warning_record_failed", error_type=type(exc).__name__)
        return None, None
    return res.get("action", "notice"), res.get("warning_count")


async def _compose_notice(
    message: Message,
    verdict: str,
    deleted: bool,
    action: str | None,
    count: int | None,
    reasons: list[str],
    language: str,
) -> str:
    """Pick the single group notice for this moderation outcome (HTML)."""
    if action == "supervisor_escalation":
        key = "warning_supervisor_escalation"
    elif action == "admin_notification":
        key = "warning_admin_notification"
    elif deleted:
        # First offence and already removed: educational notice, no admin ping.
        return get_message(
            "warning_notice", language, reasons=html.escape(", ".join(reasons))
        )
    elif verdict == "delete":
        key = "delete_failed"  # should be removed, but the bot lacks the right
    else:
        key = "flagged_content"

    mentions = await _admin_mentions(message.chat, force=action == "supervisor_escalation")
    if not mentions:
        key += "_no_admins"
    return get_message(
        key,
        language,
        reasons=html.escape(", ".join(reasons)),
        mentions=mentions,
        admin_mentions=mentions,
        mention=_offender_mention(message),
        count=count if count is not None else "?",
    )


async def _post_notice(
    message: Message, context: ContextTypes.DEFAULT_TYPE, text: str, *, reply: bool
) -> None:
    try:
        if reply:
            await message.reply_text(
                text, parse_mode=ParseMode.HTML, allow_sending_without_reply=True
            )
        else:
            # The original is gone, so it cannot be replied to.
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                message_thread_id=message.message_thread_id if message.is_topic_message else None,
            )
    except TelegramError as exc:
        logger.warning("notice_send_failed", chat_id=message.chat_id, error_type=type(exc).__name__)


async def _handle_verdict(
    message: Message, result: dict[str, Any], context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Delete the message and/or notify, based on the engine verdict."""
    verdict = result.get("verdict", "allow")
    if verdict not in ("flag", "delete"):
        return
    reasons = list(result.get("reasons") or [])
    language = result.get("language") or settings.bot_language

    logger.info(
        "moderation_action",
        verdict=verdict,
        reasons=reasons,
        language=language,
        chat_id=message.chat_id,
        message_id=message.message_id,
        edited=message.edit_date is not None,
    )

    deleted = verdict == "delete" and await _try_delete(message, context)
    action, count = await _record_warning(message, reasons)
    notice = await _compose_notice(message, verdict, deleted, action, count, reasons, language)
    await _post_notice(message, context, notice, reply=not deleted)


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Moderate a new or edited group message (text, caption and/or media)."""
    message = update.effective_message
    if message is None or message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    try:
        result = await _moderate_message(message)
        if result is not None:
            await _handle_verdict(message, result, context)
    except Exception:
        logger.exception(
            "moderation_error", chat_id=message.chat_id, message_id=message.message_id
        )


# ---------------------------------------------------------------------------
# GDPR commands
# ---------------------------------------------------------------------------

def _user_language(user: User | None) -> str:
    """The user's Telegram UI language if we ship it, else ``BOT_LANGUAGE``."""
    code = ((user.language_code if user else None) or "")[:2].lower()
    return code if code in available_languages() else settings.bot_language


async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/privacy — show the privacy notice to the requesting user."""
    message = update.effective_message
    if message is None:
        return
    lang = _user_language(message.from_user)
    await message.reply_text(get_message("privacy_notice", lang), parse_mode=ParseMode.HTML)


async def cmd_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/my_data — summarise the data stored about the user (Article 15).

    Only answered in a private chat, so nothing about a user is posted to a group.
    """
    message = update.effective_message
    if message is None or message.from_user is None:
        return
    lang = _user_language(message.from_user)
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(get_message("my_data_private_only", lang))
        return
    try:
        data = await engine_client.gdpr_export(str(message.from_user.id))
    except httpx.HTTPError as exc:
        logger.warning("gdpr_export_failed", error_type=type(exc).__name__)
        await message.reply_text(get_message("my_data_error", lang))
        return
    await message.reply_text(
        get_message(
            "my_data_summary",
            lang,
            user_hash=html.escape(str(data.get("user_id_hash", "?"))[:16]),
            events=len(data.get("moderation_events") or []),
            warnings=len(data.get("warning_records") or []),
            deletion_requests=len(data.get("deletion_requests") or []),
        ),
        parse_mode=ParseMode.HTML,
    )


async def cmd_delete_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/delete_my_data — submit an Article 17 erasure request."""
    message = update.effective_message
    if message is None:
        return

    sender = message.from_user
    if sender is None:
        return

    lang = _user_language(sender)
    try:
        result = await engine_client.gdpr_delete_request(str(sender.id))
        req_id = result.get("request_id", "?")

        # Different message if a request was already pending
        if "already pending" in result.get("message", "").lower():
            msg = get_message("delete_my_data_already_pending", lang, request_id=req_id)
        else:
            msg = get_message("delete_my_data_submitted", lang, request_id=req_id)
    except httpx.HTTPError as exc:
        # No user ID in the log — it is personal data.
        logger.warning("gdpr_delete_request_failed", error_type=type(exc).__name__)
        msg = get_message("delete_my_data_error", lang)

    await message.reply_text(msg)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _post_shutdown(application: Application) -> None:
    await engine_client.aclose()


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.bot_token)
        .concurrent_updates(_MAX_CONCURRENT_UPDATES)
        .post_shutdown(_post_shutdown)
        .build()
    )

    # GDPR commands — registered first so they win over the moderation handler;
    # they work in both groups and private chats.
    app.add_handler(CommandHandler("privacy", cmd_privacy))
    app.add_handler(CommandHandler("my_data", cmd_my_data))
    app.add_handler(CommandHandler("delete_my_data", cmd_delete_my_data))

    # Moderation — group chats only, new and edited messages alike.
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & MODERATED_CONTENT, on_message))
    return app


def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    app = build_application()
    logger.info("telegram_bot_started", engine_url=settings.engine_url)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
