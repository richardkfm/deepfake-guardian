import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { parseCommand } from "../src/commands.js";
import { MESSAGES, getMessage } from "../src/i18n.js";
import {
  MentionCooldown,
  composeNotice,
  isViolation,
  mentionTag,
  mergeResults,
  wantsAdminMentions,
  type NoticeInput,
} from "../src/moderation.js";

const ADMIN = "4915100000009@s.whatsapp.net";
const KID = "4915100000001@s.whatsapp.net";

function input(overrides: Partial<NoticeInput> = {}): NoticeInput {
  return {
    verdict: "flag",
    deleted: false,
    action: "notice",
    count: 1,
    reasons: ["nsfw"],
    language: "en",
    adminJids: [ADMIN],
    offenderJid: KID,
    ...overrides,
  };
}

describe("mergeResults", () => {
  it("takes the most severe verdict and unions reasons", () => {
    const merged = mergeResults([
      { verdict: "flag", reasons: ["cyberbullying"], language: "de" },
      { verdict: "delete", reasons: ["nsfw", "cyberbullying"] },
    ]);
    assert.deepEqual(merged, { verdict: "delete", reasons: ["cyberbullying", "nsfw"], language: "de" });
    assert.equal(mergeResults([]), null);
  });
});

describe("composeNotice", () => {
  it("flag → one admin notice that mentions admins", () => {
    const n = composeNotice(input());
    assert.match(n.text, /Flagged content \(nsfw\)\. Admins: @4915100000009/);
    assert.deepEqual(n.mentions, [ADMIN]);
  });

  it("deleted first offence → educational notice, no pings", () => {
    const n = composeNotice(input({ verdict: "delete", deleted: true }));
    assert.match(n.text, /was removed/);
    assert.deepEqual(n.mentions, []);
  });

  it("delete without admin rights → asks admins to remove it", () => {
    const n = composeNotice(input({ verdict: "delete", deleted: false }));
    assert.match(n.text, /cannot delete it/);
    assert.deepEqual(n.mentions, [ADMIN]);
  });

  it("escalation names the offender via a mention, not a raw number", () => {
    const n = composeNotice(input({ action: "admin_notification", count: 2 }));
    assert.match(n.text, /Repeated violation by @4915100000001/);
    assert.deepEqual(n.mentions, [ADMIN, KID]);
  });

  it("falls back to the no-admins variant when mentions are suppressed", () => {
    const n = composeNotice(input({ action: "supervisor_escalation", count: 3, adminJids: [] }));
    assert.match(n.text, /3 incidents recorded/);
    assert.doesNotMatch(n.text, /Admins:/);
    assert.deepEqual(n.mentions, []);
  });

  it("uses the engine-detected language", () => {
    assert.match(composeNotice(input({ language: "de" })).text, /Markierter Inhalt/);
    assert.match(composeNotice(input({ language: "xx" })).text, /Flagged content/);
  });

  it("unknown warning count renders as ?", () => {
    const n = composeNotice(input({ action: "admin_notification", count: null, adminJids: [] }));
    assert.match(n.text, /warning #\?/);
  });
});

describe("wantsAdminMentions", () => {
  it("only skips admins for a deleted first offence", () => {
    assert.equal(wantsAdminMentions(true, "notice"), false);
    assert.equal(wantsAdminMentions(true, null), false);
    assert.equal(wantsAdminMentions(true, "admin_notification"), true);
    assert.equal(wantsAdminMentions(false, "notice"), true);
  });
});

describe("MentionCooldown", () => {
  it("rate-limits per group, supervisor escalations bypass it", () => {
    let now = 0;
    const cd = new MentionCooldown(60_000, () => now);
    assert.equal(cd.tryAcquire("g1"), true);
    assert.equal(cd.tryAcquire("g1"), false);
    assert.equal(cd.tryAcquire("g2"), true);
    now = 30_000;
    assert.equal(cd.tryAcquire("g1", true), true); // forced: resets the clock to t=30s
    now = 61_000;
    assert.equal(cd.tryAcquire("g1"), false);
    now = 91_000;
    assert.equal(cd.tryAcquire("g1"), true);
  });

  it("cooldown 0 always allows", () => {
    const cd = new MentionCooldown(0, () => 0);
    assert.equal(cd.tryAcquire("g"), true);
    assert.equal(cd.tryAcquire("g"), true);
  });
});

describe("mentionTag", () => {
  it("strips server and device suffix", () => {
    assert.equal(mentionTag("4915100000001:12@s.whatsapp.net"), "@4915100000001");
  });
});

describe("parseCommand", () => {
  it("accepts / and ! prefixes, any case", () => {
    assert.equal(parseCommand("/privacy"), "privacy");
    assert.equal(parseCommand(" !Delete_My_Data "), "delete_my_data");
    assert.equal(parseCommand("/my_data"), "my_data");
  });

  it("rejects everything else", () => {
    assert.equal(parseCommand("/privacy please"), null);
    assert.equal(parseCommand("/unknown"), null);
    assert.equal(parseCommand("privacy"), null);
    assert.equal(parseCommand(undefined), null);
  });
});

describe("i18n", () => {
  const placeholders = (s: string) => new Set([...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]));

  it("every language has the same keys and placeholders as English", () => {
    for (const [lang, messages] of Object.entries(MESSAGES)) {
      assert.deepEqual(Object.keys(messages).sort(), Object.keys(MESSAGES.en).sort(), lang);
      for (const [key, template] of Object.entries(MESSAGES.en)) {
        assert.deepEqual(placeholders(messages[key]), placeholders(template), `${lang}.${key}`);
      }
    }
  });

  it("leaves unknown placeholders and returns the key when missing", () => {
    assert.equal(getMessage("nope", "en"), "nope");
    assert.match(getMessage("flagged_content", "en", { reasons: "x" }), /\{mentions\}/);
  });
});

describe("isViolation", () => {
  it("treats an unanalysable video as review-only", () => {
    assert.equal(isViolation(["unanalysable_video"]), false);
  });

  it("counts real violations even alongside review-only reasons", () => {
    assert.equal(isViolation(["nsfw"]), true);
    assert.equal(isViolation([]), true);
    assert.equal(isViolation(["unanalysable_video", "violence"]), true);
  });
});
