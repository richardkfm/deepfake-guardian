/**
 * GDPR text commands, mirroring the Telegram bot. WhatsApp has no native bot
 * commands, so a message consisting of "/privacy" or "!privacy" (any case)
 * is treated as the command.
 */

export type Command = "privacy" | "my_data" | "delete_my_data";

const COMMANDS: ReadonlySet<string> = new Set<Command>([
  "privacy",
  "my_data",
  "delete_my_data",
]);

/** Return the command in *text*, or `null` if it is not exactly a command. */
export function parseCommand(text: string | undefined): Command | null {
  const match = /^[/!]([a-z_]+)$/i.exec(text?.trim() ?? "");
  if (!match) return null;
  const name = match[1].toLowerCase();
  return COMMANDS.has(name) ? (name as Command) : null;
}
