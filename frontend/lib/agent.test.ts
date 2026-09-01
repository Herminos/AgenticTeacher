import {beforeEach, describe, expect, it, vi} from "vitest";

const api = vi.hoisted(() => ({
  assess: vi.fn(),
  compute: vi.fn(),
  retrieve: vi.fn(),
  rewrite: vi.fn(),
  streamGenerate: vi.fn(),
}));

vi.mock("./api", () => api);

beforeEach(() => {
  vi.clearAllMocks();
  api.streamGenerate.mockImplementation(async (_body, handlers) => handlers.onToken?.("回答"));
});

describe("local agent routing contract", () => {
  it("keeps the client-side orchestration module independent of Python models", async () => {
    const source = await import("./agent");
    expect(source.agentGraph).toBeDefined();
    expect(source.runAgent).toBeTypeOf("function");
  });

  it("builds a generation conversation without stale empty placeholders", async () => {
    const {conversationForRun} = await import("./agent");
    const messages = conversationForRun([
      {role: "user", content: "上一问"},
      {role: "assistant", content: "上一答"},
      {role: "assistant", content: ""},
    ], "你好");
    expect(messages).toEqual([
      {role: "user", content: "上一问"},
      {role: "assistant", content: "上一答"},
      {role: "user", content: "你好"},
    ]);
  });

  it("skips RAG when cloud rewrite returns an empty decision", async () => {
    api.rewrite.mockResolvedValue({rewritten_query: "", query_terms: [], should_retrieve: false, duration_ms: 8});
    const {runAgent} = await import("./agent");
    await runAgent({query: "你好，你是谁", subject: "calculus", modelConfig: {provider: "mock"}});
    expect(api.retrieve).not.toHaveBeenCalled();
    expect(api.assess).not.toHaveBeenCalled();
    expect(api.streamGenerate).toHaveBeenCalledWith(
      expect.objectContaining({retrieval_attempts: 0, rag_exhausted: false}),
      expect.any(Object),
      undefined,
    );
  });

  it("stops after three insufficient RAG attempts and marks fallback", async () => {
    api.rewrite.mockResolvedValue({rewritten_query: "拉普拉斯变换的定义", query_terms: ["拉普拉斯变换"], should_retrieve: true, duration_ms: 10});
    api.retrieve.mockResolvedValue({
      documents: [], retrieval_id: "retr_test",
      quality_hint: {qualified_count: 0, has_more: true, candidate_count: 15, reranked_count: 0, retrieval_ms: 12, reranker_ms: 20},
    });
    api.assess.mockResolvedValue({sufficient: false, missing_aspects: ["定义"], next_query: "拉普拉斯变换的数学定义", duration_ms: 6});
    const {runAgent} = await import("./agent");
    await runAgent({query: "拉普拉斯变换是什么", subject: "calculus", modelConfig: {provider: "mock"}});
    expect(api.retrieve).toHaveBeenCalledTimes(3);
    expect(api.assess).toHaveBeenCalledTimes(3);
    expect(api.streamGenerate).toHaveBeenCalledWith(
      expect.objectContaining({retrieval_attempts: 3, rag_exhausted: true}),
      expect.any(Object),
      undefined,
    );
  });
});
