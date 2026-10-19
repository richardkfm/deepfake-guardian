/**
 * Extract what needs moderating from a raw Baileys message.
 *
 * Unwraps view-once, ephemeral (disappearing) and document-with-caption
 * wrappers, so these cannot be used to bypass moderation, and maps edits
 * back to the key of the original message (the one to delete).
 */

import {
  jidNormalizedUser,
  normalizeMessageContent,
  proto,
  type WAMessage,
  type WAMessageKey,
} from "@whiskeysockets/baileys";

export type MediaKind = "image" | "video";

export interface MediaInfo {
  kind: MediaKind;
  /** image / video / sticker / document / ptv — for logs */
  source: string;
  /** Size in bytes as announced by the sender, if known. */
  fileLength?: number;
  /** Embedded low-res JPEG preview — moderated instead of oversized media. */
  thumbnail?: Uint8Array;
}

export interface ModeratableContent {
  /** Text, or the caption of a media message. */
  text?: string;
  media?: MediaInfo;
  /** Key of the message to delete (for an edit: the original message). */
  targetKey: WAMessageKey;
  edited: boolean;
}

type Content = proto.IMessage;
type LongLike = number | { toString(): string } | null | undefined;

function toNumber(value: LongLike): number | undefined {
  if (value === null || value === undefined) return undefined;
  const n = typeof value === "number" ? value : Number(value.toString());
  return Number.isFinite(n) ? n : undefined;
}

export function textOf(content: Content | undefined): string | undefined {
  if (!content) return undefined;
  const text =
    content.conversation ||
    content.extendedTextMessage?.text ||
    content.imageMessage?.caption ||
    content.videoMessage?.caption ||
    content.documentMessage?.caption;
  return text || undefined;
}

export function mediaOf(content: Content | undefined): MediaInfo | undefined {
  if (!content) return undefined;
  const info = (
    kind: MediaKind,
    source: string,
    m: { fileLength?: LongLike; jpegThumbnail?: Uint8Array | null }
  ): MediaInfo => ({
    kind,
    source,
    fileLength: toNumber(m.fileLength),
    thumbnail: m.jpegThumbnail?.length ? m.jpegThumbnail : undefined,
  });

  if (content.imageMessage) return info("image", "image", content.imageMessage);
  // Includes GIFs, which WhatsApp sends as videos with gifPlayback.
  if (content.videoMessage) return info("video", "video", content.videoMessage);
  if (content.ptvMessage) return info("video", "ptv", content.ptvMessage);
  // WebP — the engine decodes animated stickers via their first frame.
  if (content.stickerMessage) return info("image", "sticker", content.stickerMessage);
  const doc = content.documentMessage;
  if (doc) {
    const mime = (doc.mimetype ?? "").toLowerCase();
    if (mime.startsWith("image/") && mime !== "image/svg+xml") {
      return info("image", "document", doc);
    }
    if (mime.startsWith("video/")) return info("video", "document", doc);
  }
  return undefined;
}

/** Return the moderatable parts of *message*, or `null` if there are none. */
export function extractContent(message: WAMessage): ModeratableContent | null {
  const content = normalizeMessageContent(message.message);
  if (!content) return null;

  const protocol = content.protocolMessage;
  if (protocol) {
    // Revokes, ephemeral settings, … carry nothing to moderate. Edits do:
    // only the new text/caption — the media itself cannot be changed.
    if (
      protocol.type !== proto.Message.ProtocolMessage.Type.MESSAGE_EDIT ||
      !protocol.editedMessage
    ) {
      return null;
    }
    const text = textOf(normalizeMessageContent(protocol.editedMessage));
    if (!text) return null;
    return {
      text,
      edited: true,
      targetKey: {
        remoteJid: message.key.remoteJid,
        participant: message.key.participant,
        id: protocol.key?.id ?? message.key.id,
        fromMe: false,
      },
    };
  }

  const text = textOf(content);
  const media = mediaOf(content);
  if (!text && !media) return null;
  return { text, media, targetKey: message.key, edited: false };
}

/** Normalised JID of whoever sent *message* (group participant or 1:1 chat). */
export function senderJid(message: WAMessage): string | undefined {
  const raw = message.key.participant || message.key.remoteJid;
  return raw ? jidNormalizedUser(raw) : undefined;
}

export function isGroupJid(jid: string | null | undefined): boolean {
  return jid?.endsWith("@g.us") === true;
}
