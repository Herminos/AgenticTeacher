export type Route = "compute" | "rag" | "hybrid" | "error";

export interface DocumentItem {
  text: string;
  metadata: {source_id: string; chunk_id: string; filename?: string; page?: number; chapter?: string; [key: string]: unknown};
  score?: number;
  normalized_score?: number;
  score_type?: string;
}

export interface TraceEvent {
  event_id: string;
  stream: "agent" | "service";
  seq: number;
  step: "router" | "rewrite" | "retrieve" | "grade" | "compute" | "generate";
  status: "queued" | "running" | "succeeded" | "failed" | "skipped";
  duration_ms?: number;
  summary?: string;
  retry_reason?: string;
}

export interface ChatMessage {role: "user" | "assistant"; content: string;}

export type ProviderId = "mock" | "deepseek" | "qwen" | "openai";

/** Kept in memory by the UI and sent only to the backend for the active run. */
export interface ModelConfig {
  provider: ProviderId;
  base_url?: string;
  api_key?: string;
  model?: string;
  temperature?: number;
  api_key_configured?: boolean;
}
