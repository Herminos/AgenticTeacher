import {afterEach, describe, expect, it, vi} from "vitest";

import {streamGenerate} from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("generation SSE client", () => {
  it("accepts token events followed by done", async () => {
    const body = [
      "event: token",
      'data: {"request_id":"req_ok","stream":"generate","seq":1,"content":"你好"}',
      "",
      "event: done",
      'data: {"request_id":"req_ok","stream":"generate","seq":2,"finish":true,"usage":{}}',
      "",
    ].join("\n");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, {status: 200})));
    const tokens: string[] = [];
    await streamGenerate({}, {onToken: (token) => tokens.push(token)});
    expect(tokens).toEqual(["你好"]);
  });

  it("surfaces the backend validation message for HTTP 422", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: {code: "VALIDATION_ERROR", message: "request validation failed", retryable: false},
    }), {status: 422, headers: {"Content-Type": "application/json"}})));
    await expect(streamGenerate({}, {})).rejects.toThrow("request validation failed");
  });

  it("does not treat a truncated stream as success", async () => {
    const body = [
      "event: token",
      'data: {"request_id":"req_cut","stream":"generate","seq":1,"content":"半截回答"}',
      "",
    ].join("\n");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, {status: 200})));
    await expect(streamGenerate({}, {})).rejects.toThrow("生成连接意外中断");
  });
});
