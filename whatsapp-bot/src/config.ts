import "dotenv/config";

/** Read a non-negative number from the environment, falling back on bad input. */
export function numberEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return fallback;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

export const config = {
  engineUrl: process.env.ENGINE_URL ?? "http://localhost:8000",
  engineApiKey: process.env.ENGINE_API_KEY ?? "",
  sessionDataPath: process.env.SESSION_DATA_PATH ?? "./auth_info",
  logLevel: process.env.LOG_LEVEL ?? "info",
  /** Language for group notices when the engine reports none ("en" | "de"). */
  botLanguage: process.env.BOT_LANGUAGE ?? "en",
  /** Per-request engine timeout. Video moderation is the slow path. */
  engineTimeoutMs: numberEnv("ENGINE_TIMEOUT_SECONDS", 60) * 1000,
  /** Media larger than this is not downloaded (0 = no limit). */
  maxMediaBytes: Math.floor(numberEnv("MAX_MEDIA_MB", 20) * 1024 * 1024),
  /** Min. seconds between two admin @-mentions in the same group (0 = always). */
  adminMentionCooldownMs: numberEnv("ADMIN_MENTION_COOLDOWN_SECONDS", 60) * 1000,
} as const;
