"""Tests for message handling and verdict actions in ``main.py``.

Telegram objects are replaced with lightweight mocks; the engine client is
patched, so no network access is needed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import BadRequest

import main
from config import settings

# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    main._admin_cache.clear()
    main._bot_rights_cache.clear()
    main._last_admin_mention.clear()
    monkeypatch.setattr(settings, "admin_mention_cooldown_seconds", 60.0)
    monkeypatch.setattr(settings, "max_media_mb", 20.0)
    monkeypatch.setattr(settings, "bot_language", "en")
    yield


def _user(uid=42, username=None, first_name="Alex", is_bot=False, language_code=None):
    user = MagicMock()
    user.id = uid
    user.username = username
    user.first_name = first_name
    user.is_bot = is_bot
    user.language_code = language_code
    user.mention_html.return_value = f'<a href="tg://user?id={uid}">{first_name}</a>'
    return user


def _file_obj(data=b"bytes", file_size=1000, thumbnail=None, **extra):
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(data))
    obj = MagicMock()
    obj.get_file = AsyncMock(return_value=tg_file)
    obj.file_size = file_size
    obj.thumbnail = thumbnail
    for key, value in extra.items():
        setattr(obj, key, value)
    return obj


def _message(
    *,
    text=None,
    caption=None,
    chat_type=ChatType.SUPERGROUP,
    admins=None,
    bot_member=None,
    sender=None,
    **media,
):
    msg = MagicMock()
    msg.text = text
    msg.caption = caption
    msg.chat_id = -100123
    msg.message_id = 7
    msg.edit_date = None
    msg.is_topic_message = False
    msg.message_thread_id = None
    msg.sender_chat = None
    msg.from_user = sender if sender is not None else _user()
    for attr in ("photo", "video", "animation", "video_note", "sticker", "document"):
        setattr(msg, attr, media.get(attr, [] if attr == "photo" else None))
    msg.chat.id = msg.chat_id
    msg.chat.type = chat_type
    msg.chat.get_administrators = AsyncMock(return_value=admins or [])
    msg.chat.get_chat_member = AsyncMock(
        return_value=bot_member or SimpleNamespace(status=ChatMemberStatus.MEMBER)
    )
    msg.delete = AsyncMock()
    msg.reply_text = AsyncMock()
    return msg


def _context():
    ctx = MagicMock()
    ctx.bot.id = 999
    ctx.bot.send_message = AsyncMock()
    return ctx


def _admin(username=None, uid=1, is_bot=False):
    return SimpleNamespace(user=_user(uid=uid, username=username, is_bot=is_bot))


def _can_delete_member():
    return SimpleNamespace(status=ChatMemberStatus.ADMINISTRATOR, can_delete_messages=True)


def _update(message):
    return SimpleNamespace(effective_message=message)


# ---------------------------------------------------------------------------
# extract_media
# ---------------------------------------------------------------------------


class TestExtractMedia:
    def test_photo_uses_highest_resolution(self):
        small, big = _file_obj(file_size=10), _file_obj(file_size=99)
        media = main.extract_media(_message(photo=[small, big]))
        assert media.kind == "image" and media.file is big

    def test_animation_wins_over_document(self):
        anim = _file_obj()
        msg = _message(animation=anim, document=_file_obj(mime_type="video/mp4"))
        media = main.extract_media(msg)
        assert media.source == "animation" and media.kind == "video" and media.file is anim

    def test_video_note(self):
        assert main.extract_media(_message(video_note=_file_obj())).kind == "video"

    @pytest.mark.parametrize(
        ("mime", "kind"),
        [("image/jpeg", "image"), ("video/mp4", "video"), ("application/pdf", None),
         ("image/svg+xml", None)],
    )
    def test_document_by_mime(self, mime, kind):
        media = main.extract_media(_message(document=_file_obj(mime_type=mime)))
        assert (media.kind if media else None) == kind

    def test_static_and_video_stickers(self):
        static = _file_obj(is_animated=False, is_video=False)
        video = _file_obj(is_animated=False, is_video=True)
        assert main.extract_media(_message(sticker=static)).kind == "image"
        assert main.extract_media(_message(sticker=video)).kind == "video"

    def test_animated_sticker_uses_thumbnail(self):
        thumb = _file_obj()
        sticker = _file_obj(is_animated=True, is_video=False, thumbnail=thumb)
        media = main.extract_media(_message(sticker=sticker))
        assert media.kind == "image" and media.file is thumb

    def test_text_only_has_no_media(self):
        assert main.extract_media(_message(text="hi")) is None


class TestSelectDownload:
    def test_within_limit(self):
        media = main.MediaRef("video", "video", "FILE", 1024)
        assert main._select_download(media) == ("video", "FILE")

    def test_too_large_falls_back_to_thumbnail(self):
        media = main.MediaRef("video", "video", "FILE", 50 * 1024 * 1024, "THUMB")
        assert main._select_download(media) == ("image", "THUMB")

    def test_too_large_without_thumbnail_is_skipped(self):
        media = main.MediaRef("video", "document", "FILE", 50 * 1024 * 1024)
        assert main._select_download(media) is None

    def test_zero_disables_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "max_media_mb", 0.0)
        media = main.MediaRef("video", "video", "FILE", 10**12)
        assert main._select_download(media) == ("video", "FILE")


# ---------------------------------------------------------------------------
# merge_results
# ---------------------------------------------------------------------------


def test_merge_results_takes_most_severe_and_unions_reasons():
    merged = main.merge_results([
        {"verdict": "flag", "reasons": ["cyberbullying"], "language": "de"},
        {"verdict": "delete", "reasons": ["nsfw", "cyberbullying"], "language": None},
    ])
    assert merged == {"verdict": "delete", "reasons": ["cyberbullying", "nsfw"], "language": "de"}
    assert main.merge_results([]) is None


# ---------------------------------------------------------------------------
# on_message — engine interaction
# ---------------------------------------------------------------------------

_ALLOW = {"verdict": "allow", "reasons": []}


class TestOnMessage:
    async def test_caption_and_photo_are_both_moderated(self):
        msg = _message(caption="look", photo=[_file_obj(data=b"img")])
        with (
            patch.object(main.engine_client, "moderate_text", AsyncMock(return_value=_ALLOW)) as mt,
            patch.object(main.engine_client, "moderate_image", AsyncMock(return_value=_ALLOW)) as mi,
        ):
            await main.on_message(_update(msg), _context())
        mt.assert_awaited_once()
        assert mt.call_args.args == ("look",)
        assert mi.call_args.args == (b"img",)
        assert mi.call_args.kwargs == {"user_id": "42", "group_id": "-100123"}

    async def test_text_delete_skips_media_download(self):
        photo = _file_obj()
        msg = _message(caption="bad", photo=[photo])
        with (
            patch.object(main.engine_client, "moderate_text",
                         AsyncMock(return_value={"verdict": "delete", "reasons": ["violence"]})),
            patch.object(main.engine_client, "moderate_image", AsyncMock()) as mi,
            patch.object(main, "_handle_verdict", AsyncMock()) as hv,
        ):
            await main.on_message(_update(msg), _context())
        mi.assert_not_called()
        photo.get_file.assert_not_called()
        assert hv.call_args.args[1]["verdict"] == "delete"

    async def test_engine_down_fails_open(self):
        msg = _message(text="hello")
        with patch.object(main.engine_client, "moderate_text",
                          AsyncMock(side_effect=httpx.ConnectError("down"))):
            await main.on_message(_update(msg), _context())
        msg.delete.assert_not_called()
        msg.reply_text.assert_not_called()

    async def test_private_chat_ignored(self):
        msg = _message(text="hello", chat_type=ChatType.PRIVATE)
        with patch.object(main.engine_client, "moderate_text", AsyncMock()) as mt:
            await main.on_message(_update(msg), _context())
        mt.assert_not_called()

    async def test_media_download_error_does_not_crash(self):
        photo = _file_obj()
        photo.get_file = AsyncMock(side_effect=BadRequest("File is too big"))
        msg = _message(photo=[photo])
        with patch.object(main.engine_client, "moderate_image", AsyncMock()) as mi:
            await main.on_message(_update(msg), _context())
        mi.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_verdict — actions
# ---------------------------------------------------------------------------


def _warn(action="notice", count=1):
    return AsyncMock(return_value={"action": action, "warning_count": count})


class TestHandleVerdict:
    async def test_allow_does_nothing(self):
        msg = _message(text="x")
        with patch.object(main.engine_client, "record_warning", _warn()) as rw:
            await main._handle_verdict(msg, _ALLOW, _context())
        rw.assert_not_called()
        msg.reply_text.assert_not_called()

    async def test_delete_as_admin_posts_notice_without_reply(self):
        msg = _message(text="x", bot_member=_can_delete_member())
        ctx = _context()
        with patch.object(main.engine_client, "record_warning", _warn()):
            await main._handle_verdict(msg, {"verdict": "delete", "reasons": ["violence"]}, ctx)
        msg.delete.assert_awaited_once()
        # A deleted message cannot be replied to — the notice is a plain send.
        msg.reply_text.assert_not_called()
        ctx.bot.send_message.assert_awaited_once()
        text = ctx.bot.send_message.call_args.kwargs["text"]
        assert "violence" in text and "removed" in text

    async def test_admin_without_delete_right_asks_admins(self):
        member = SimpleNamespace(
            status=ChatMemberStatus.ADMINISTRATOR, can_delete_messages=False
        )
        msg = _message(text="x", bot_member=member, admins=[_admin("teacher")])
        with patch.object(main.engine_client, "record_warning", _warn()):
            await main._handle_verdict(msg, {"verdict": "delete", "reasons": ["nsfw"]}, _context())
        msg.delete.assert_not_called()
        msg.reply_text.assert_awaited_once()
        text = msg.reply_text.call_args.args[0]
        assert "@teacher" in text and "cannot delete" in text

    async def test_delete_failure_falls_back_to_admin_notice(self):
        msg = _message(text="x", bot_member=_can_delete_member(), admins=[_admin("teacher")])
        msg.delete = AsyncMock(side_effect=BadRequest("Message can't be deleted"))
        with patch.object(main.engine_client, "record_warning", _warn()):
            await main._handle_verdict(msg, {"verdict": "delete", "reasons": ["nsfw"]}, _context())
        msg.reply_text.assert_awaited_once()
        assert "cannot delete" in msg.reply_text.call_args.args[0]
        # Cached rights are dropped so the next message re-checks them.
        assert msg.chat_id not in main._bot_rights_cache

    async def test_flag_sends_single_message(self):
        msg = _message(text="x", admins=[_admin("teacher")])
        with patch.object(main.engine_client, "record_warning", _warn()) as rw:
            await main._handle_verdict(msg, {"verdict": "flag", "reasons": ["nsfw"]}, _context())
        rw.assert_awaited_once()
        # One notice only — and not the "your message was removed" text.
        msg.reply_text.assert_awaited_once()
        text = msg.reply_text.call_args.args[0]
        assert "@teacher" in text and "removed" not in text

    async def test_admins_without_username_get_link_mention(self):
        msg = _message(text="x", admins=[_admin(None, uid=5), _admin("botty", is_bot=True)])
        with patch.object(main.engine_client, "record_warning", _warn()):
            await main._handle_verdict(msg, {"verdict": "flag", "reasons": ["nsfw"]}, _context())
        text = msg.reply_text.call_args.args[0]
        assert 'tg://user?id=5' in text and "@botty" not in text

    async def test_escalation_message_replaces_flag_notice(self):
        msg = _message(text="x", admins=[_admin("teacher")], sender=_user(username="kid"))
        with patch.object(main.engine_client, "record_warning", _warn("admin_notification", 2)):
            await main._handle_verdict(msg, {"verdict": "flag", "reasons": ["nsfw"]}, _context())
        msg.reply_text.assert_awaited_once()
        text = msg.reply_text.call_args.args[0]
        assert "Repeated violation by @kid" in text and "@teacher" in text

    async def test_admin_mentions_rate_limited_per_chat(self):
        ctx = _context()
        with patch.object(main.engine_client, "record_warning", _warn()):
            first = _message(text="x", admins=[_admin("teacher")])
            await main._handle_verdict(first, {"verdict": "flag", "reasons": ["nsfw"]}, ctx)
            second = _message(text="y", admins=[_admin("teacher")])
            await main._handle_verdict(second, {"verdict": "flag", "reasons": ["nsfw"]}, ctx)
        assert "@teacher" in first.reply_text.call_args.args[0]
        assert "@teacher" not in second.reply_text.call_args.args[0]
        # The admin list is cached, too.
        second.chat.get_administrators.assert_not_called()

    async def test_supervisor_escalation_bypasses_cooldown(self):
        ctx = _context()
        main._last_admin_mention[-100123] = main.time.monotonic()
        msg = _message(text="x", admins=[_admin("teacher")])
        with patch.object(main.engine_client, "record_warning", _warn("supervisor_escalation", 3)):
            await main._handle_verdict(msg, {"verdict": "flag", "reasons": ["nsfw"]}, ctx)
        assert "@teacher" in msg.reply_text.call_args.args[0]

    async def test_warning_failure_still_notifies(self):
        msg = _message(text="x", admins=[_admin("teacher")])
        with patch.object(main.engine_client, "record_warning",
                          AsyncMock(side_effect=httpx.ConnectError("down"))):
            await main._handle_verdict(msg, {"verdict": "flag", "reasons": ["nsfw"]}, _context())
        msg.reply_text.assert_awaited_once()

    async def test_reason_text_is_html_escaped(self):
        msg = _message(text="x")
        with patch.object(main.engine_client, "record_warning", _warn()):
            await main._handle_verdict(msg, {"verdict": "flag", "reasons": ["<b>"]}, _context())
        assert "&lt;b&gt;" in msg.reply_text.call_args.args[0]

    async def test_uses_engine_detected_language(self):
        msg = _message(text="x")
        with patch.object(main.engine_client, "record_warning", _warn()):
            await main._handle_verdict(
                msg, {"verdict": "flag", "reasons": ["nsfw"], "language": "de"}, _context()
            )
        assert "Markierter Inhalt" in msg.reply_text.call_args.args[0]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


class TestCommands:
    async def test_privacy_uses_user_language_and_html(self):
        msg = _message(sender=_user(language_code="de-DE"))
        await main.cmd_privacy(_update(msg), _context())
        text = msg.reply_text.call_args.args[0]
        assert "Datenschutzhinweis" in text and "/delete_my_data" in text
        assert msg.reply_text.call_args.kwargs["parse_mode"] == "HTML"

    async def test_my_data_refused_in_group(self):
        msg = _message()
        with patch.object(main.engine_client, "gdpr_export", AsyncMock()) as ex:
            await main.cmd_my_data(_update(msg), _context())
        ex.assert_not_called()
        assert "private chat" in msg.reply_text.call_args.args[0]

    async def test_my_data_summary_in_private_chat(self):
        msg = _message(chat_type=ChatType.PRIVATE)
        export = {
            "user_id_hash": "abcdef0123456789ffff",
            "moderation_events": [{}, {}],
            "warning_records": [{}],
            "deletion_requests": [],
        }
        with patch.object(main.engine_client, "gdpr_export", AsyncMock(return_value=export)):
            await main.cmd_my_data(_update(msg), _context())
        text = msg.reply_text.call_args.args[0]
        assert "abcdef0123456789" in text and "ffff" not in text
        assert "Moderation events: 2" in text and "Warning records: 1" in text

    async def test_delete_my_data_error_does_not_log_user_id(self):
        msg = _message(sender=_user(uid=123456789))
        with (
            patch.object(main.engine_client, "gdpr_delete_request",
                         AsyncMock(side_effect=httpx.ConnectError("down"))),
            patch.object(main, "logger") as log,
        ):
            await main.cmd_delete_my_data(_update(msg), _context())
        assert "123456789" not in str(log.mock_calls)
        assert "Could not submit" in msg.reply_text.call_args.args[0]

    async def test_delete_my_data_already_pending(self):
        msg = _message()
        resp = {"request_id": 3, "status": "pending", "message": "A deletion request is already pending."}
        with patch.object(main.engine_client, "gdpr_delete_request", AsyncMock(return_value=resp)):
            await main.cmd_delete_my_data(_update(msg), _context())
        assert "already pending" in msg.reply_text.call_args.args[0]


def test_application_wiring_registers_commands_before_moderation(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "123:ABC")
    app = main.build_application()
    handlers = app.handlers[0]
    names = [type(h).__name__ for h in handlers]
    assert names == ["CommandHandler"] * 3 + ["MessageHandler"]
    assert app.update_processor.max_concurrent_updates == main._MAX_CONCURRENT_UPDATES
