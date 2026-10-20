/**
 * WhatsApp moderation bot using Baileys.
 *
 * Connects to WhatsApp via QR code, listens for group messages — text,
 * captions, images, videos/GIFs, round videos, stickers, image/video
 * documents, view-once and disappearing messages, and edits — and moderates
 * them through the engine API. Mirrors the Telegram bot:
 *
 * - `delete` → removed if the bot is a group admin, otherwise admins are asked
 * - `flag`   → admins are asked to review
 * - every violation is recorded via /warnings/record and escalates
 * - one group notice per moderated message, admin mentions rate-limited
 * - fail-open: if the engine is unreachable the message is left alone and
 *   `engine_unavailable_fail_open` is logged
 * - GDPR commands: /privacy, /my_data (private chat), /delete_my_data
 */

import makeWASocket, {
  areJidsSameUser,
  DisconnectReason,
  downloadMediaMessage,
  useMultiFileAuthState,
  type GroupMetadata,
  type GroupParticipant,
  type WAMessage,
  type WASocket,
} from "@whiskeysockets/baileys";
import pino from "pino";
import qrcode from "qrcode-terminal";

import { parseCommand, type Command } from "./commands.js";
import { config } from "./config.js";
import {
  extractContent,
  isGroupJid,
  senderJid,
  type ModeratableContent,
} from "./content.js";
import {
  describeError,
  gdprDeleteRequest,
  gdprExport,
  moderateImage,
  moderateText,
  moderateVideo,
  recordWarning,
  type AuditContext,
  type EscalationAction,
  type ModerationResult,
} from "./engine-client.js";
import { getMessage } from "./i18n.js";
import { logger } from "./logger.js";
import {
  composeNotice,
  isViolation,
  MentionCooldown,
  mergeResults,
  wantsAdminMentions,
} from "./moderation.js";

const baileysLogger = pino({ level: "silent" });

// ---------------------------------------------------------------------------
// Group metadata (cached)
// ---------------------------------------------------------------------------
const GROUP_CACHE_TTL_MS = 5 * 60 * 1000;
const groupCache = new Map<string, { at: number; metadata: GroupMetadata }>();
const mentionCooldown = new MentionCooldown(config.adminMentionCooldownMs);

async function getGroupMetadata(
  sock: WASocket,
  jid: string
): Promise<GroupMetadata | null> {
  const cached = groupCache.get(jid);
  if (cached && Date.now() - cached.at < GROUP_CACHE_TTL_MS) {
    return cached.metadata;
  }
  try {
    const metadata = await sock.groupMetadata(jid);
    groupCache.set(jid, { at: Date.now(), metadata });
    return metadata;
  } catch (err) {
    logger.warn({ jid, ...describeError(err) }, "group_metadata_failed");
    return null;
  }
}

function isMe(sock: WASocket, participant: GroupParticipant): boolean {
  const me = sock.user;
  if (!me) return false;
  const ids = [participant.id, participant.jid, participant.lid];
  return ids.some(
    (id) =>
      id !== undefined &&
      (areJidsSameUser(id, me.id) || areJidsSameUser(id, me.lid))
  );
}

function botIsAdmin(sock: WASocket, metadata: GroupMetadata): boolean {
  return metadata.participants.some((p) => Boolean(p.admin) && isMe(sock, p));
}

function adminJids(sock: WASocket, metadata: GroupMetadata): string[] {
  return metadata.participants
    .filter((p) => Boolean(p.admin) && !isMe(sock, p))
    .map((p) => p.id);
}

// ---------------------------------------------------------------------------
// Engine calls
// ---------------------------------------------------------------------------

async function callEngine(
  contentType: string,
  fn: () => Promise<ModerationResult>
): Promise<ModerationResult | null> {
  try {
    return await fn();
  } catch (err) {
    logger.warn(
      { contentType, ...describeError(err), detail: "message left unmoderated" },
      "engine_unavailable_fail_open"
    );
    return null;
  }
}

async function downloadMedia(
  sock: WASocket,
  message: WAMessage,
  content: ModeratableContent
): Promise<{ kind: "image" | "video"; data: Buffer } | null> {
  const media = content.media;
  if (!media) return null;

  const tooLarge =
    config.maxMediaBytes > 0 &&
    media.fileLength !== undefined &&
    media.fileLength > config.maxMediaBytes;
  if (tooLarge) {
    const meta = { source: media.source, fileLength: media.fileLength, maxBytes: config.maxMediaBytes };
    if (media.thumbnail) {
      logger.info(meta, "media_too_large_using_thumbnail");
      return { kind: "image", data: Buffer.from(media.thumbnail) };
    }
    logger.warn(meta, "media_too_large_skipped");
    return null;
  }

  try {
    const data = await downloadMediaMessage(
      message,
      "buffer",
      {},
      { logger: baileysLogger, reuploadRequest: sock.updateMediaMessage }
    );
    return { kind: media.kind, data };
  } catch (err) {
    logger.warn({ source: media.source, ...describeError(err) }, "media_download_failed");
    return null;
  }
}

async function moderateContent(
  sock: WASocket,
  message: WAMessage,
  content: ModeratableContent,
  ctx: AuditContext
): Promise<ModerationResult | null> {
  const results: ModerationResult[] = [];

  if (content.text) {
    const text = content.text;
    const res = await callEngine("text", () => moderateText(text, ctx));
    if (res) {
      results.push(res);
      // Already being removed — no need to download the media too.
      if (res.verdict === "delete") return mergeResults(results);
    }
  }

  const media = await downloadMedia(sock, message, content);
  if (media) {
    const { kind, data } = media;
    const fn = kind === "image" ? moderateImage : moderateVideo;
    const res = await callEngine(kind, () => fn(data, ctx));
    if (res) results.push(res);
  }

  return mergeResults(results);
}

// ---------------------------------------------------------------------------
// Verdict handling
// ---------------------------------------------------------------------------

async function handleVerdict(
  sock: WASocket,
  message: WAMessage,
  content: ModeratableContent,
  result: ModerationResult
): Promise<void> {
  const jid = message.key.remoteJid;
  if (!jid || result.verdict === "allow") return;
  const reasons = result.reasons ?? [];
  const language = result.language || config.botLanguage;

  logger.info(
    { verdict: result.verdict, reasons, language, jid, messageId: message.key.id, edited: content.edited },
    "moderation_action"
  );

  const metadata = await getGroupMetadata(sock, jid);

  // Deleting someone else's message silently does nothing unless we are an
  // admin, so check first instead of relying on sendMessage() to throw.
  let deleted = false;
  if (result.verdict === "delete" && metadata && botIsAdmin(sock, metadata)) {
    try {
      await sock.sendMessage(jid, { delete: content.targetKey });
      deleted = true;
      logger.info({ jid, messageId: content.targetKey.id }, "message_deleted");
    } catch (err) {
      groupCache.delete(jid);
      logger.warn({ jid, ...describeError(err) }, "message_delete_failed");
    }
  }

  let action: EscalationAction | null = null;
  let count: number | null = null;
  const sender = senderJid(message);
  if (sender && isViolation(reasons)) {
    try {
      const warning = await recordWarning(sender, jid, reasons);
      action = warning.action;
      count = warning.warning_count;
    } catch (err) {
      logger.warn(describeError(err), "warning_record_failed");
    }
  }

  let admins: string[] = [];
  if (
    metadata &&
    wantsAdminMentions(deleted, action) &&
    mentionCooldown.tryAcquire(jid, action === "supervisor_escalation")
  ) {
    admins = adminJids(sock, metadata);
  }

  const notice = composeNotice({
    verdict: result.verdict,
    deleted,
    action,
    count,
    reasons,
    language,
    adminJids: admins,
    offenderJid: sender,
  });

  try {
    await sock.sendMessage(
      jid,
      { text: notice.text, mentions: notice.mentions },
      // A deleted message cannot be quoted.
      deleted ? undefined : { quoted: message }
    );
  } catch (err) {
    logger.warn({ jid, ...describeError(err) }, "notice_send_failed");
  }
}

// ---------------------------------------------------------------------------
// GDPR commands
// ---------------------------------------------------------------------------

async function handleCommand(
  sock: WASocket,
  message: WAMessage,
  command: Command
): Promise<void> {
  const jid = message.key.remoteJid;
  const sender = senderJid(message);
  if (!jid || !sender) return;
  const lang = config.botLanguage;
  let text: string;

  if (command === "privacy") {
    text = getMessage("privacy_notice", lang);
  } else if (command === "my_data") {
    if (isGroupJid(jid)) {
      text = getMessage("my_data_private_only", lang);
    } else {
      try {
        const data = await gdprExport(sender);
        text = getMessage("my_data_summary", lang, {
          user_hash: String(data.user_id_hash ?? "?").slice(0, 16),
          events: data.moderation_events?.length ?? 0,
          warnings: data.warning_records?.length ?? 0,
          deletion_requests: data.deletion_requests?.length ?? 0,
        });
      } catch (err) {
        logger.warn(describeError(err), "gdpr_export_failed");
        text = getMessage("my_data_error", lang);
      }
    }
  } else {
    try {
      const res = await gdprDeleteRequest(sender);
      const key = (res.message ?? "").toLowerCase().includes("already pending")
        ? "delete_my_data_already_pending"
        : "delete_my_data_submitted";
      text = getMessage(key, lang, { request_id: res.request_id ?? "?" });
    } catch (err) {
      // No user ID in the log — it is personal data (a phone number).
      logger.warn(describeError(err), "gdpr_delete_request_failed");
      text = getMessage("delete_my_data_error", lang);
    }
  }

  try {
    await sock.sendMessage(jid, { text }, { quoted: message });
  } catch (err) {
    logger.warn({ jid, ...describeError(err) }, "command_reply_failed");
  }
}

// ---------------------------------------------------------------------------
// Message processing
// ---------------------------------------------------------------------------

async function processMessage(
  sock: WASocket,
  message: WAMessage
): Promise<void> {
  if (message.key.fromMe) return; // Don't moderate own messages
  const jid = message.key.remoteJid;
  if (!jid || jid === "status@broadcast") return;

  try {
    const content = extractContent(message);
    if (!content) return;

    const command = content.edited ? null : parseCommand(content.text);
    if (command) {
      await handleCommand(sock, message, command);
      return;
    }

    if (!isGroupJid(jid)) return; // moderation is group-only

    const ctx: AuditContext = { userId: senderJid(message), groupId: jid };
    const result = await moderateContent(sock, message, content, ctx);
    if (result) {
      await handleVerdict(sock, message, content, result);
    }
  } catch (err) {
    logger.error(
      { messageId: message.key.id, ...describeError(err) },
      "moderation_error"
    );
  }
}

// ---------------------------------------------------------------------------
// Connection
// ---------------------------------------------------------------------------
let reconnectAttempts = 0;

async function startBot(): Promise<void> {
  const { state, saveCreds } = await useMultiFileAuthState(
    config.sessionDataPath
  );

  const sock = makeWASocket({
    auth: state,
    logger: baileysLogger,
    printQRInTerminal: false,
  });

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      logger.info("Scan the QR code below to connect:");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      const statusCode = (
        lastDisconnect?.error as { output?: { statusCode?: number } } | undefined
      )?.output?.statusCode;
      if (statusCode === DisconnectReason.loggedOut) {
        logger.error(
          { statusCode },
          `logged_out — delete ${config.sessionDataPath} and restart to pair again`
        );
        return;
      }
      const delayMs = Math.min(30_000, 1000 * 2 ** reconnectAttempts++);
      logger.info({ statusCode, delayMs }, "connection_closed_reconnecting");
      setTimeout(() => {
        startBot().catch((err) =>
          logger.error(describeError(err), "reconnect_failed")
        );
      }, delayMs);
    } else if (connection === "open") {
      reconnectAttempts = 0;
      logger.info("whatsapp_bot_connected");
    }
  });

  sock.ev.on("creds.update", saveCreds);

  // New messages (type "notify") and ones received while offline ("append").
  sock.ev.on("messages.upsert", async ({ messages }) => {
    for (const msg of messages) {
      await processMessage(sock, msg);
    }
  });
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

logger.info({ engineUrl: config.engineUrl }, "starting_whatsapp_bot");
startBot().catch((err) => {
  logger.fatal(describeError(err), "failed_to_start_bot");
  process.exit(1);
});
