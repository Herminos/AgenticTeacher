// Use LangGraph's browser-safe entrypoint. The default entrypoint imports
// node:async_hooks, which Next.js cannot bundle for a client component.
import {Annotation, END, START, StateGraph} from "@langchain/langgraph/web";
import {assess, compute, retrieve, rewrite, streamGenerate} from "./api";
import type {ChatMessage, DocumentItem, ModelConfig, Route, TraceEvent} from "./types";

export interface AgentInput {query: string; subject: string; messages?: ChatMessage[]; fileIds?: string[]; modelConfig?: ModelConfig; signal?: AbortSignal; onEvent?: (event: TraceEvent) => void; onDocuments?: (documents: DocumentItem[]) => void; onToken?: (text: string) => void; onSource?: (sourceId: string) => void;}
export interface AgentResult {route: Route; final_answer: string; documents: DocumentItem[]; rewritten_query: string; trace: TraceEvent[]; retrieval_id?: string; compute_result?: {result: string; warnings: string[]; verified: boolean};}

const MAX_ITERATIONS = Math.max(1, Math.min(3, Number(process.env.NEXT_PUBLIC_MAX_ITERATIONS || 3)));
function id(prefix: string) { return `${prefix}_${crypto.randomUUID().slice(0, 12)}`; }
function trace(step: TraceEvent["step"], status: TraceEvent["status"], summary: string, seq: number, retry_reason?: string, duration_ms?: number): TraceEvent {
  return {event_id: id("evt"), stream: "agent", seq, step, status, summary, retry_reason, duration_ms};
}
function looksComputational(query: string) { return /(求导|积分|解方程|求值|d\/dx|∫|integrate\(|diff\(|solve\(|[a-zA-Z]\s*[=＋+−\-*/^])/i.test(query); }
function wantsExplanation(query: string) { return /(为什么|原理|解释|讲解|条件|证明|区别|概念)/.test(query); }

export function conversationForRun(history: ChatMessage[], query: string): ChatMessage[] {
  const completeHistory = history.filter((message) => message.content.trim().length > 0);
  return [...completeHistory, {role: "user", content: query}];
}

const GraphState = Annotation.Root({query: Annotation<string>(), rewritten_query: Annotation<string>({reducer: (_, next) => next, default: () => ""}), documents: Annotation<DocumentItem[]>({reducer: (_, next) => next, default: () => []}), iteration: Annotation<number>({reducer: (_, next) => next, default: () => 0}), route: Annotation<Route>({reducer: (_, next) => next, default: () => "rag"}), final_answer: Annotation<string>({reducer: (_, next) => next, default: () => ""})});

// This compiled graph documents the local orchestration topology. runAgent below keeps
// callbacks and browser AbortSignals explicit, which is easier to consume from React.
export const agentGraph = new StateGraph(GraphState)
  .addNode("router", (state: any) => state)
  .addNode("rewrite", (state: any) => state)
  .addNode("retrieve", (state: any) => state)
  .addNode("grade", (state: any) => state)
  .addNode("compute", (state: any) => state)
  .addNode("generate", (state: any) => state)
  .addEdge(START, "router")
  // Keep both pure-compute and regular requests explicit. The runtime router
  // below performs the same decision with richer signals and handles hybrid
  // compute after grading.
  .addConditionalEdges(
    "router",
    (state: any) => state.route === "compute" ? "compute" : "rewrite",
    {compute: "compute", rewrite: "rewrite"},
  )
  .addConditionalEdges(
    "compute",
    (state: any) => state.route === "compute" ? END : "generate",
    {compute: END, generate: "generate"},
  )
  .addEdge("rewrite", "retrieve")
  .addEdge("retrieve", "grade")
  .addConditionalEdges(
    "grade",
    (state: any) => state.route === "hybrid" ? "compute" : "generate",
    {compute: "compute", generate: "generate"},
  )
  .addEdge("generate", END)
  .compile();

export async function runAgent(input: AgentInput): Promise<AgentResult> {
  const runStarted = performance.now();
  const runId = id("run"); let localSeq = 0; const events: TraceEvent[] = [];
  const emit = (event: TraceEvent) => { events.push(event); input.onEvent?.(event); };
  const add = (step: TraceEvent["step"], status: TraceEvent["status"], summary: string, retry?: string, durationMs?: number) => emit(trace(step, status, summary, ++localSeq, retry, durationMs));
  const common = {subject: input.subject, agent_run_id: runId, ...(input.modelConfig ? {llm: input.modelConfig} : {})};
  const messages = input.messages?.filter((message) => message.content.trim().length > 0) || [];
  if (!messages.length) messages.push({role: "user", content: input.query});
  let route: Route = looksComputational(input.query) ? (wantsExplanation(input.query) ? "hybrid" : "compute") : "rag";
  add("router", "succeeded", `路由：${route}`);

  if (route === "compute") {
    try {
      add("compute", "running", "正在调用符号计算服务...");
      const result = await compute({expression: input.query, timeout_ms: 3000, ...common}, input.signal);
      add("compute", "succeeded", "计算完成", undefined, result.duration_ms);
      return {route, final_answer: result.result, documents: [], rewritten_query: "", trace: events, compute_result: {result: result.result, warnings: result.warnings || [], verified: result.verified || false}};
    } catch (error) {
      add("compute", "failed", "计算服务未能完成", String(error));
      route = "rag";
    }
  }

  let rewritten = input.query; let documents: DocumentItem[] = []; let retrievalId: string | undefined;
  let retrievalAttempts = 0; let evidenceSufficient = false; let ragExhausted = false;
  add("rewrite", "running", "正在由云端模型判断并改写教学检索问题...");
  const rewrittenResponse = await rewrite({query: input.query, previous_query: "", missing_aspects: [], ...common}, input.signal);
  rewritten = rewrittenResponse.rewritten_query;
  if (!rewrittenResponse.should_retrieve) {
    add("rewrite", "skipped", "该问题不需要教学资料检索，云端模型返回空 JSON", undefined, rewrittenResponse.duration_ms);
    add("retrieve", "skipped", "已跳过 RAG");
  } else {
    add("rewrite", "succeeded", rewritten, undefined, rewrittenResponse.duration_ms);
    for (let attempt = 1; attempt <= MAX_ITERATIONS; attempt += 1) {
      add("retrieve", "running", `第 ${attempt}/3 轮：召回子块并使用 Qwen Reranker 精排...`);
      const retrieved = await retrieve({query: rewritten, ...common}, input.signal);
      retrievalAttempts = attempt;
      documents = retrieved.documents as DocumentItem[]; retrievalId = retrieved.retrieval_id;
      // Publish each successful retrieval immediately. The UI can therefore
      // show the selected parent blocks inside the Agent flow even if the
      // subsequent cloud generation request fails.
      input.onDocuments?.(documents);
      const retrievalDuration = retrieved.quality_hint.retrieval_ms + retrieved.quality_hint.reranker_ms;
      const matchedChildren = documents.reduce((total, document) => {
        const count = Number(document.metadata.matched_child_count ?? 1);
        return total + (Number.isFinite(count) && count > 0 ? count : 1);
      }, 0);
      add("retrieve", "succeeded", `召回 ${retrieved.quality_hint.candidate_count} 个子块候选，重排命中 ${matchedChildren} 个子块并映射为 ${documents.length} 个父块`, undefined, retrievalDuration);
      add("grade", "running", "云端模型正在判断教材证据是否足够...");
      // The evidence-review contract accepts at most five documents. Retrieval
      // may be configured with a larger parent TopK for UI exploration, but
      // the cloud reviewer should receive the highest-ranked complete parents
      // only (never raw child chunks).
      const reviewDocuments = documents.slice(0, 5);
      const assessment = await assess({
        query: input.query,
        rewritten_query: rewritten,
        documents: reviewDocuments.map((doc) => ({text: doc.text, source_id: doc.metadata.source_id, normalized_score: doc.normalized_score ?? null})),
        attempt,
        ...common,
      }, input.signal);
      evidenceSufficient = assessment.sufficient;
      add("grade", evidenceSufficient ? "succeeded" : "failed", evidenceSufficient ? "教材证据充足" : `仍缺少：${assessment.missing_aspects.join("、")}`, evidenceSufficient ? undefined : "根据知识缺口继续检索", assessment.duration_ms);
      if (evidenceSufficient) break;
      rewritten = assessment.next_query;
    }
    ragExhausted = !evidenceSufficient && retrievalAttempts === MAX_ITERATIONS;
    if (ragExhausted) {
      add("grade", "failed", "三轮 RAG 均未找到理想片段，将明确标注并使用模型通用知识", "RAG_EXHAUSTED");
      retrievalId = undefined;
    }
  }

  if (route === "hybrid" && /[=＋+\-*/^]|\d/.test(input.query)) {
    try {
      add("compute", "running", "正在补充符号计算结果...");
      const result = await compute({expression: input.query, timeout_ms: 3000, ...common}, input.signal);
      add("compute", "succeeded", "计算结果已加入回答上下文", undefined, result.duration_ms);
      messages.push({role: "assistant", content: `工具计算结果：${result.result}`});
    } catch (error) { add("compute", "failed", "计算部分未完成，将仅依据教材解释", String(error)); }
  }

  add("generate", "running", "正在生成回答...");
  let answer = "";
  // Keep GenerateRequest within its declared source/context limits even when
  // the management UI is configured to return more parent blocks.
  const generationDocuments = ragExhausted ? [] : documents.slice(0, 16);
  const generationContext = generationDocuments.map((doc, index) => `[S${index + 1}] ${doc.text}`).join("\n\n").slice(0, 100000);
  await streamGenerate({messages, context: generationContext, file_ids: input.fileIds || [], sources: generationDocuments.map((doc) => ({source_id: doc.metadata.source_id, citation: `${doc.metadata.filename || "教材"} p.${doc.metadata.page || "?"}`})), retrieval_id: retrievalId, retrieval_attempts: retrievalAttempts, rag_exhausted: ragExhausted, ...common}, {
    onToken: (text) => { answer += text; input.onToken?.(text); },
    onSource: input.onSource,
    onTrace: input.onEvent,
    onError: (message) => add("generate", "failed", message),
  }, input.signal);
  add("generate", "succeeded", "Agent 全流程完成", undefined, Math.round((performance.now() - runStarted) * 100) / 100);
  return {route, final_answer: answer, documents, rewritten_query: rewritten, retrieval_id: retrievalId, trace: events};
}
