"use client";

import {create} from "zustand";
import {persist} from "zustand/middleware";
import {conversationForRun, runAgent} from "@/lib/agent";
import type {ChatMessage, DocumentItem, ModelConfig, TraceEvent} from "@/lib/types";

interface ChatState {
  messages: ChatMessage[];
  trace: TraceEvent[];
  documents: DocumentItem[];
  isLoading: boolean;
  error: string | null;
  cancel: () => void;
  send: (query: string, subject: string, fileIds?: string[], modelConfig?: ModelConfig) => Promise<void>;
  reset: () => void;
}

let activeController: AbortController | null = null;

export const useAgenticChat = create<ChatState>()(persist((set, get) => ({
  messages: [], trace: [], documents: [], isLoading: false, error: null,
  cancel: () => { activeController?.abort(); activeController = null; set({isLoading: false}); },
  reset: () => { activeController?.abort(); activeController = null; set({messages: [], trace: [], documents: [], error: null, isLoading: false}); },
  send: async (query, subject, fileIds = [], modelConfig) => {
    activeController?.abort(); activeController = new AbortController();
    const conversation = conversationForRun(get().messages, query);
    set({messages: [...conversation, {role: "assistant", content: ""}], trace: [], documents: [], isLoading: true, error: null});
    try {
      const result = await runAgent({
        query, subject, fileIds, modelConfig, messages: conversation, signal: activeController.signal,
        onEvent: (event) => set((state) => ({trace: [...state.trace, event]})),
        onToken: (text) => set((state) => {
          const messages = [...state.messages]; const last = messages[messages.length - 1];
          messages[messages.length - 1] = {...last, content: `${last?.content || ""}${text}`}; return {messages};
        }),
        onSource: () => undefined,
      });
      set((state) => {
        const messages = [...state.messages]; const last = messages[messages.length - 1];
        if (last?.role === "assistant" && !last.content && result.final_answer) messages[messages.length - 1] = {...last, content: result.final_answer};
        return {messages, documents: result.documents, isLoading: false};
      }); activeController = null;
    } catch (error) {
      if (activeController?.signal.aborted) { activeController = null; set({isLoading: false}); return; }
      const message = error instanceof Error ? error.message : "请求失败";
      set((state) => ({isLoading: false, error: message, messages: state.messages.map((item, index) => index === state.messages.length - 1 ? {...item, content: `抱歉，处理失败：${message}`} : item)})); activeController = null;
    }
  },
}), {name: "agentic-teacher-session", partialize: (state) => ({messages: state.messages})}));
