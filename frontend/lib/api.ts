import {z} from "zod";
import type {DocumentItem, TraceEvent} from "./types";

const baseUrl = (process.env.NEXT_PUBLIC_AI_API_URL || "http://localhost:8000/v1").replace(/\/$/, "");

const errorSchema = z.object({error: z.object({code: z.string(), message: z.string(), retryable: z.boolean().optional(), request_id: z.string().nullable().optional()})});
const documentSchema = z.object({text: z.string(), metadata: z.record(z.unknown()), score: z.number().nullable().optional(), normalized_score: z.number().nullable().optional(), score_type: z.string().nullable().optional()});
const retrieveSchema = z.object({documents: z.array(documentSchema), quality_hint: z.object({qualified_count: z.number(), has_more: z.boolean(), candidate_count: z.number(), reranked_count: z.number(), retrieval_ms: z.number(), reranker_ms: z.number()}), retrieval_id: z.string()});
const rewriteSchema = z.object({rewritten_query: z.string(), query_terms: z.array(z.string()).default([]), should_retrieve: z.boolean(), duration_ms: z.number()});
const assessSchema = z.object({sufficient: z.boolean(), missing_aspects: z.array(z.string()), next_query: z.string(), duration_ms: z.number()});
const computeSchema = z.object({result: z.string(), warnings: z.array(z.string()).default([]), verified: z.boolean().default(false), duration_ms: z.number().default(0)});
const providerSchema = z.object({id: z.string(), label: z.string(), base_url: z.string(), model: z.string(), models: z.array(z.string()), kind: z.string()});
const indexedFileSchema = z.object({filename: z.string(), chunks: z.number(), status: z.enum(["indexed", "skipped", "failed"]), error: z.string().nullable().optional()});
const indexResponseSchema = z.object({index_id: z.string(), collection: z.string(), subject: z.string().nullable().optional(), status: z.enum(["completed", "partial", "failed"]), duration_ms: z.number(), files_received: z.number(), files_indexed: z.number(), chunks: z.number(), added_chunks: z.number(), hyde_count: z.number(), embedding_model: z.string(), files: z.array(indexedFileSchema), warnings: z.array(z.string())});

async function fetchJson<T>(path: string, body: unknown, schema: z.ZodSchema<T>, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 30000);
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, {once: true});
  try {
    const response = await fetch(`${baseUrl}${path}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal: controller.signal});
    const data: unknown = await response.json();
    if (!response.ok) {
      const parsed = errorSchema.safeParse(data);
      throw new Error(parsed.success ? parsed.data.error.message : `API error ${response.status}`);
    }
    return schema.parse(data);
  } finally {
    globalThis.clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

export function rewrite(body: Record<string, unknown>, signal?: AbortSignal) { return fetchJson("/rewrite", body, rewriteSchema, signal); }
export function assess(body: Record<string, unknown>, signal?: AbortSignal) { return fetchJson("/assess", body, assessSchema, signal); }
export function retrieve(body: Record<string, unknown>, signal?: AbortSignal) { return fetchJson("/retrieve", body, retrieveSchema, signal); }
export function compute(body: Record<string, unknown>, signal?: AbortSignal) { return fetchJson("/compute", body, computeSchema, signal); }

export async function listProviders(signal?: AbortSignal) {
  const response = await fetch(`${baseUrl}/providers`, {signal});
  const data: unknown = await response.json();
  if (!response.ok) throw new Error("无法读取模型供应商列表");
  return z.object({providers: z.array(providerSchema)}).parse(data).providers;
}

export async function upload(file: File, purpose: "answer_attachment" | "ingest_source" = "answer_attachment", signal?: AbortSignal) {
  const form = new FormData(); form.append("file", file); form.append("purpose", purpose);
  const response = await fetch(`${baseUrl}/files`, {method: "POST", body: form, signal});
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error?.message || data?.detail?.message || "文件上传失败");
  return z.object({file_id: z.string(), status: z.string(), expires_at: z.string(), job_id: z.string().nullable().optional()}).parse(data);
}

export type IndexResult = z.infer<typeof indexResponseSchema>;

export async function indexFiles(files: File[], subject: string, hydeCount = 0, signal?: AbortSignal): Promise<IndexResult> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file, (file as File & {webkitRelativePath?: string}).webkitRelativePath || file.name));
  form.append("subject", subject);
  form.append("hyde_count", String(Math.max(0, Math.min(3, Math.floor(hydeCount)))));
  const response = await fetch(`${baseUrl}/index`, {method: "POST", body: form, signal});
  if (!response.ok) {
    const error = await responseError(response, `RAG Index 失败（HTTP ${response.status}）`);
    throw error;
  }
  return indexResponseSchema.parse(await response.json());
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  try {
    const data: unknown = await response.json();
    const parsed = errorSchema.safeParse(data);
    if (parsed.success) return new Error(parsed.data.error.message);
  } catch { /* the upstream response was not JSON */ }
  return new Error(fallback);
}

export async function streamGenerate(body: Record<string, unknown>, handlers: {onToken?: (text: string) => void; onTrace?: (event: TraceEvent) => void; onSource?: (sourceId: string) => void; onError?: (message: string) => void; onDone?: (usage: Record<string, unknown>) => void}, signal?: AbortSignal) {
  const response = await fetch(`${baseUrl}/generate`, {method: "POST", headers: {"Content-Type": "application/json", Accept: "text/event-stream"}, body: JSON.stringify(body), signal});
  if (!response.ok) throw await responseError(response, `生成请求失败（HTTP ${response.status}）`);
  if (!response.body) throw new Error("生成响应不包含可读取的数据流");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = ""; let eventName = "message"; let dataLines: string[] = [];
  const seen = new Set<string>();
  let streamError = "";
  let doneReceived = false;
  const flush = (block: string) => {
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    try {
      const data = JSON.parse(dataLines.join("\n")) as {request_id?: string; stream?: string; seq?: number; content?: string; source_id?: string; message?: string; summary?: string; step?: string; status?: string; duration_ms?: number; usage?: Record<string, unknown>};
      const key = `${data.request_id || ""}:${data.stream || "generate"}:${data.seq ?? -1}`;
      if (seen.has(key)) return; seen.add(key);
      if (eventName === "token" && data.content) handlers.onToken?.(data.content);
      else if (eventName === "source" && data.source_id) handlers.onSource?.(data.source_id);
      else if (eventName === "error") { streamError = data.message || "生成失败"; handlers.onError?.(streamError); }
      else if (eventName === "done") { doneReceived = true; handlers.onDone?.(data.usage || {}); }
      else if (eventName === "trace" && data.step && data.status) handlers.onTrace?.({event_id: key, stream: "service", seq: data.seq || 0, step: data.step as TraceEvent["step"], status: data.status as TraceEvent["status"], summary: data.summary, duration_ms: data.duration_ms});
    } catch { /* ignore malformed heartbeat */ }
    dataLines = []; eventName = "message";
  };
  while (true) {
    const {value, done} = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
    const blocks = buffer.split("\n\n"); buffer = blocks.pop() || "";
    blocks.forEach(flush);
    if (done) { if (buffer) flush(buffer); break; }
  }
  if (streamError) throw new Error(streamError);
  if (!doneReceived) throw new Error("生成连接意外中断，请重试");
}
