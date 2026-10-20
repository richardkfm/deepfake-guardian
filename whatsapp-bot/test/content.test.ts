import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { proto, type WAMessage } from "@whiskeysockets/baileys";

import { extractContent, isGroupJid, senderJid } from "../src/content.js";

const GROUP = "120363000000000000@g.us";
const ALICE = "4915100000001@s.whatsapp.net";

function msg(message: proto.IMessage, key: Partial<WAMessage["key"]> = {}): WAMessage {
  return {
    key: { remoteJid: GROUP, participant: ALICE, id: "MSG1", fromMe: false, ...key },
    message,
  } as WAMessage;
}

describe("extractContent", () => {
  it("reads plain and extended text", () => {
    assert.equal(extractContent(msg({ conversation: "hi" }))?.text, "hi");
    assert.equal(extractContent(msg({ extendedTextMessage: { text: "link" } }))?.text, "link");
  });

  it("reads image caption and media together", () => {
    const c = extractContent(msg({ imageMessage: { caption: "look", fileLength: 1234 } }));
    assert.equal(c?.text, "look");
    assert.deepEqual(c?.media, { kind: "image", source: "image", fileLength: 1234, thumbnail: undefined });
  });

  it("unwraps view-once and disappearing messages", () => {
    const viewOnce = msg({ viewOnceMessageV2: { message: { imageMessage: {} } } });
    assert.equal(extractContent(viewOnce)?.media?.kind, "image");
    const ephemeral = msg({ ephemeralMessage: { message: { videoMessage: { caption: "x" } } } });
    assert.equal(extractContent(ephemeral)?.media?.kind, "video");
    assert.equal(extractContent(ephemeral)?.text, "x");
  });

  it("classifies stickers, round videos and documents", () => {
    assert.equal(extractContent(msg({ stickerMessage: {} }))?.media?.kind, "image");
    assert.equal(extractContent(msg({ ptvMessage: {} }))?.media?.kind, "video");
    const docImg = msg({ documentMessage: { mimetype: "image/png" } });
    assert.equal(extractContent(docImg)?.media?.source, "document");
    const docVid = msg({ documentWithCaptionMessage: { message: { documentMessage: { mimetype: "video/mp4", caption: "c" } } } });
    assert.equal(extractContent(docVid)?.media?.kind, "video");
    assert.equal(extractContent(docVid)?.text, "c");
    assert.equal(extractContent(msg({ documentMessage: { mimetype: "application/pdf" } })), null);
    assert.equal(extractContent(msg({ documentMessage: { mimetype: "image/svg+xml" } })), null);
  });

  it("keeps the embedded thumbnail", () => {
    const thumb = new Uint8Array([1, 2, 3]);
    const c = extractContent(msg({ videoMessage: { jpegThumbnail: thumb, fileLength: 99 } }));
    assert.deepEqual(c?.media?.thumbnail, thumb);
  });

  it("maps an edit to the original message key", () => {
    const edit = msg(
      {
        protocolMessage: {
          type: proto.Message.ProtocolMessage.Type.MESSAGE_EDIT,
          key: { id: "ORIGINAL" },
          editedMessage: { conversation: "now harmful" },
        },
      },
      { id: "EDIT-EVENT" }
    );
    const c = extractContent(edit);
    assert.equal(c?.text, "now harmful");
    assert.equal(c?.edited, true);
    assert.equal(c?.targetKey.id, "ORIGINAL");
    assert.equal(c?.targetKey.participant, ALICE);
    assert.equal(c?.targetKey.remoteJid, GROUP);
  });

  it("ignores revokes and empty messages", () => {
    const revoke = msg({
      protocolMessage: { type: proto.Message.ProtocolMessage.Type.REVOKE, key: { id: "X" } },
    });
    assert.equal(extractContent(revoke), null);
    assert.equal(extractContent(msg({})), null);
    assert.equal(extractContent({ key: {} } as WAMessage), null);
  });
});

describe("senderJid / isGroupJid", () => {
  it("uses the participant in groups and the chat in 1:1", () => {
    assert.equal(senderJid(msg({ conversation: "x" }, { participant: "4915100000001:3@s.whatsapp.net" })), ALICE);
    assert.equal(senderJid(msg({ conversation: "x" }, { remoteJid: ALICE, participant: undefined })), ALICE);
  });

  it("recognises group JIDs", () => {
    assert.equal(isGroupJid(GROUP), true);
    assert.equal(isGroupJid(ALICE), false);
    assert.equal(isGroupJid(undefined), false);
  });
});
