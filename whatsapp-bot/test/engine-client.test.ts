import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";

import { numberEnv } from "../src/config.js";
import { describeError, isRetryable } from "../src/engine-client.js";

function axiosError(opts: { status?: number; code?: string } = {}): AxiosError {
  const config = {
    headers: new AxiosHeaders({ "X-API-Key": "secret-key" }),
    data: JSON.stringify({ text: "private message text" }),
  };
  const response = opts.status
    ? ({ status: opts.status, data: {}, headers: {}, statusText: "", config } as AxiosResponse)
    : undefined;
  return new AxiosError("boom", opts.code, config, undefined, response);
}

describe("isRetryable", () => {
  it("retries connection failures and gateway errors", () => {
    assert.equal(isRetryable(axiosError({ code: "ECONNREFUSED" })), true);
    assert.equal(isRetryable(axiosError({ status: 503 })), true);
    assert.equal(isRetryable(axiosError({ status: 500 })), true);
  });

  it("does not retry client errors or timeouts", () => {
    assert.equal(isRetryable(axiosError({ status: 401 })), false);
    assert.equal(isRetryable(axiosError({ status: 422 })), false);
    assert.equal(isRetryable(axiosError({ code: "ECONNABORTED" })), false);
    assert.equal(isRetryable(axiosError({ code: "ETIMEDOUT" })), false);
    assert.equal(isRetryable(new Error("other")), false);
  });
});

describe("describeError", () => {
  it("never exposes the request payload or API key", () => {
    const info = describeError(axiosError({ status: 500, code: "ERR_BAD_RESPONSE" }));
    assert.deepEqual(info, { errorType: "AxiosError", code: "ERR_BAD_RESPONSE", status: 500 });
    const serialised = JSON.stringify(info);
    assert.doesNotMatch(serialised, /private message text|secret-key/);
  });

  it("handles non-axios errors", () => {
    assert.deepEqual(describeError(new TypeError("x")), { errorType: "TypeError" });
    assert.deepEqual(describeError("x"), { errorType: "string" });
  });
});

describe("numberEnv", () => {
  it("falls back on missing, invalid or negative values", () => {
    const name = "DG_TEST_NUMBER";
    delete process.env[name];
    assert.equal(numberEnv(name, 5), 5);
    for (const [raw, expected] of [["", 5], ["12.5", 12.5], ["0", 0], ["abc", 5], ["-1", 5]] as const) {
      process.env[name] = raw;
      assert.equal(numberEnv(name, 5), expected, raw);
    }
    delete process.env[name];
  });
});
