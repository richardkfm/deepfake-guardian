/**
 * HTTP client for the moderation engine API.
 *
 * Retries transient failures (engine not reachable yet, 5xx) with exponential
 * backoff. Deliberately *not* retried: 4xx (bad API key / payload — retrying
 * cannot help) and timeouts (the engine is still busy, usually with a video;
 * re-sending only multiplies the load).
 *
 * Errors are logged through {@link describeError}, never as raw AxiosErrors:
 * those carry the request config, i.e. the message text / media payload and
 * the X-API-Key header.
 */

import axios, { AxiosError, type AxiosInstance } from "axios";

import { config } from "./config.js";
import { logger } from "./logger.js";

export const PLATFORM = "whatsapp";

export interface ModerationScores {
  violence: number;
  sexual_violence: number;
  nsfw: number;
  deepfake_suspect: number;
  cyberbullying?: number;
  extra?: Record<string, number>;
}

export type Verdict = "allow" | "delete" | "flag";

export interface ModerationResult {
  verdict: Verdict;
  reasons: string[];
  scores?: ModerationScores;
  language?: string | null;
}

export type EscalationAction =
  | "notice"
  | "admin_notification"
  | "supervisor_escalation";

export interface WarningResult {
  warning_count: number;
  action: EscalationAction;
}

export interface DeleteRequestResult {
  request_id: number;
  status: string;
  message: string;
}

export interface ExportResult {
  user_id_hash: string;
  moderation_events: unknown[];
  warning_records: unknown[];
  deletion_requests: unknown[];
}

/** Audit context; the engine hashes these IDs before storing anything. */
export interface AuditContext {
  userId?: string;
  groupId?: string;
}

// ---------------------------------------------------------------------------
// Retry configuration
// ---------------------------------------------------------------------------
const MAX_RETRIES = 3;
const BACKOFF_FACTOR_MS = 1000; // 1s → 2s → 4s
const RETRY_STATUS_CODES = new Set([500, 502, 503, 504]);
const TIMEOUT_CODES = new Set(["ECONNABORTED", "ETIMEDOUT"]);

// ---------------------------------------------------------------------------
// HTTP client
// ---------------------------------------------------------------------------
const headers: Record<string, string> = {};
if (config.engineApiKey) {
  headers["X-API-Key"] = config.engineApiKey;
}

const client: AxiosInstance = axios.create({
  baseURL: config.engineUrl,
  timeout: config.engineTimeoutMs,
  headers,
  // Large videos as base64 exceed axios' default body limits.
  maxBodyLength: Infinity,
  maxContentLength: Infinity,
});

// ---------------------------------------------------------------------------
// Error helpers
// ---------------------------------------------------------------------------

/** Log-safe summary of an error: type, code and HTTP status only. */
export function describeError(err: unknown): {
  errorType: string;
  code?: string;
  status?: number;
} {
  if (err instanceof AxiosError) {
    return {
      errorType: "AxiosError",
      code: err.code,
      status: err.response?.status,
    };
  }
  if (err instanceof Error) {
    return { errorType: err.name };
  }
  return { errorType: typeof err };
}

/** Whether a failed request is worth sending again. */
export function isRetryable(err: unknown): boolean {
  if (!(err instanceof AxiosError)) return false;
  if (err.response) return RETRY_STATUS_CODES.has(err.response.status);
  // No response: retry connection failures, but not timeouts.
  return !TIMEOUT_CODES.has(err.code ?? "");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function postWithRetry<T>(path: string, data: unknown): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      const { data: responseData } = await client.post<T>(path, data);
      return responseData;
    } catch (err) {
      const info = describeError(err);
      if (info.status === 401 || info.status === 403) {
        logger.error(
          { path, status: info.status },
          "engine_auth_failed — ENGINE_API_KEY must match the engine's API_KEY"
        );
      }
      if (!isRetryable(err) || attempt >= MAX_RETRIES) throw err;
      const waitMs = BACKOFF_FACTOR_MS * 2 ** attempt;
      logger.warn(
        { path, attempt: attempt + 1, waitMs, ...info },
        "engine_request_retry"
      );
      await sleep(waitMs);
    }
  }
}

function auditFields(ctx: AuditContext): Record<string, string> {
  const fields: Record<string, string> = { platform: PLATFORM };
  if (ctx.userId) fields.user_id = ctx.userId;
  if (ctx.groupId) fields.group_id = ctx.groupId;
  return fields;
}

// ---------------------------------------------------------------------------
// Public API — moderation
// ---------------------------------------------------------------------------
export async function moderateText(
  text: string,
  ctx: AuditContext = {}
): Promise<ModerationResult> {
  return postWithRetry<ModerationResult>("/moderate_text", {
    text,
    ...auditFields(ctx),
  });
}

export async function moderateImage(
  imageBytes: Buffer,
  ctx: AuditContext = {}
): Promise<ModerationResult> {
  return postWithRetry<ModerationResult>("/moderate_image", {
    image_base64: imageBytes.toString("base64"),
    ...auditFields(ctx),
  });
}

export async function moderateVideo(
  videoBytes: Buffer,
  ctx: AuditContext = {}
): Promise<ModerationResult> {
  return postWithRetry<ModerationResult>("/moderate_video", {
    video_base64: videoBytes.toString("base64"),
    ...auditFields(ctx),
  });
}

// ---------------------------------------------------------------------------
// Public API — warnings & GDPR
// ---------------------------------------------------------------------------
export async function recordWarning(
  userId: string,
  groupId: string,
  reasons: string[]
): Promise<WarningResult> {
  return postWithRetry<WarningResult>("/warnings/record", {
    user_id: userId,
    group_id: groupId,
    platform: PLATFORM,
    reasons,
  });
}

export async function gdprDeleteRequest(
  userId: string
): Promise<DeleteRequestResult> {
  return postWithRetry<DeleteRequestResult>("/gdpr/delete_request", {
    user_id: userId,
    platform: PLATFORM,
    notes: "requested via /delete_my_data",
  });
}

export async function gdprExport(userId: string): Promise<ExportResult> {
  return postWithRetry<ExportResult>("/gdpr/export", {
    user_id: userId,
    platform: PLATFORM,
  });
}
