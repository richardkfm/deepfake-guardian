import pino from "pino";

import { config } from "./config.js";

/** Shared structured logger. Log metadata only — never message text or media. */
export const logger = pino({ level: config.logLevel });
