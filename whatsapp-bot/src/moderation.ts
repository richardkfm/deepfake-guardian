/**
 * Pure verdict-handling logic (no sockets), mirroring the Telegram bot:
 * at most one group notice per moderated message, admin @-mentions
 * rate-limited per group, supervisor escalations always mention.
 */

import type {
  EscalationAction,
  ModerationResult,
  Verdict,
} from "./engine-client.js";
import { getMessage } from "./i18n.js";

const SEVERITY: Record<Verdict, number> = { allow: 0, flag: 1, delete: 2 };

/** Combine text + media results: most severe verdict, union of reasons. */
export function mergeResults(
  results: ModerationResult[]
): ModerationResult | null {
  if (results.length === 0) return null;
  let verdict: Verdict = "allow";
  const reasons: string[] = [];
  let language: string | null = null;
  for (const r of results) {
    if ((SEVERITY[r.verdict] ?? 0) > SEVERITY[verdict]) verdict = r.verdict;
    for (const reason of r.reasons ?? []) {
      if (!reasons.includes(reason)) reasons.push(reason);
    }
    language ??= r.language ?? null;
  }
  return { verdict, reasons, language };
}

/**
 * Engine reasons that ask for human review but are not the sender's fault
 * (e.g. a video the engine could not decode) — no warning is recorded.
 */
export const REVIEW_ONLY_REASONS: ReadonlySet<string> = new Set([
  "unanalysable_video",
]);

/** Whether *reasons* contain an actual violation worth a warning. */
export function isViolation(reasons: string[]): boolean {
  return reasons.length === 0 || reasons.some((r) => !REVIEW_ONLY_REASONS.has(r));
}

/** Text that WhatsApp renders as a mention of *jid* (paired with `mentions`). */
export function mentionTag(jid: string): string {
  return `@${jid.split("@")[0].split(":")[0]}`;
}

/** Per-group cooldown for @-mentioning all admins. */
export class MentionCooldown {
  private readonly last = new Map<string, number>();

  constructor(
    private readonly cooldownMs: number,
    private readonly now: () => number = Date.now
  ) {}

  /** Whether admins may be mentioned now; records the mention if so. */
  tryAcquire(groupId: string, force = false): boolean {
    const now = this.now();
    const last = this.last.get(groupId);
    if (
      !force &&
      this.cooldownMs > 0 &&
      last !== undefined &&
      now - last < this.cooldownMs
    ) {
      return false;
    }
    this.last.set(groupId, now);
    return true;
  }
}

export interface NoticeInput {
  verdict: Verdict;
  deleted: boolean;
  action: EscalationAction | null;
  count: number | null;
  reasons: string[];
  language: string;
  /** Admin JIDs to mention (already filtered by the cooldown; may be empty). */
  adminJids: string[];
  offenderJid?: string;
}

export interface Notice {
  text: string;
  mentions: string[];
}

/** Whether the notice for this outcome @-mentions admins (only then fetch them). */
export function wantsAdminMentions(
  deleted: boolean,
  action: EscalationAction | null
): boolean {
  return (
    !deleted ||
    action === "admin_notification" ||
    action === "supervisor_escalation"
  );
}

/** Pick and render the single group notice for a moderation outcome. */
export function composeNotice(input: NoticeInput): Notice {
  const reasons = input.reasons.join(", ");
  let key: string;
  if (input.action === "supervisor_escalation") {
    key = "warning_supervisor_escalation";
  } else if (input.action === "admin_notification") {
    key = "warning_admin_notification";
  } else if (input.deleted) {
    // First offence and already removed: educational notice, no admin ping.
    return { text: getMessage("warning_notice", input.language, { reasons }), mentions: [] };
  } else if (input.verdict === "delete") {
    key = "delete_failed"; // should be removed, but the bot is not admin
  } else {
    key = "flagged_content";
  }

  if (input.adminJids.length === 0) key += "_no_admins";
  const text = getMessage(key, input.language, {
    reasons,
    mentions: input.adminJids.map(mentionTag).join(" "),
    mention: input.offenderJid ? mentionTag(input.offenderJid) : "",
    count: input.count ?? "?",
  });
  // Listing a JID in `mentions` makes WhatsApp render "@<number>" as the
  // contact's name, so the offender's phone number is not printed raw.
  const mentions = [...input.adminJids];
  if (input.offenderJid && text.includes(mentionTag(input.offenderJid))) {
    mentions.push(input.offenderJid);
  }
  return { text, mentions };
}
