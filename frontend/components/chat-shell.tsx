"use client";

import {FormEvent, useEffect, useMemo, useRef, useState} from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {useDropzone} from "react-dropzone";
import {BookOpen, ChevronDown, ChevronRight, FileImage, Loader2, Paperclip, Plus, Send, Sigma, Sparkles, Upload, X} from "lucide-react";
import {Button} from "@/components/ui/button";
import {listRagIndexes, upload} from "@/lib/api";
import {useAgenticChat} from "@/hooks/useAgenticChat";
import {ModelSettings} from "@/components/model-settings";
import type {ModelConfig} from "@/lib/types";

// KaTeX and the Markdown parser are client-only. Dynamic loading avoids
// bundling parser-side DOM assumptions into the Next.js server render.
const MarkdownView = dynamic(() => import("@/components/markdown-renderer").then((module) => module.MarkdownRenderer), {
  ssr: false,
  loading: () => <div className="whitespace-pre-wrap text-[15px] leading-7 text-slate-300">正在渲染内容…</div>,
});

const subjects = [{id: "calculus", label: "微积分"}, {id: "linear_algebra", label: "线性代数"}, {id: "physics", label: "大学物理"}, {id: "chemistry", label: "化学"}, {id: "programming", label: "C / 算法"}];
const subjectStorageKey = "agentic-teacher-subject";
const latexShortcuts = ["\\frac{}{}", "\\int", "\\sum", "\\alpha", "\\beta", "\\partial"];

function isKnownSubject(value: string | null | undefined): value is string {
  return Boolean(value && subjects.some((item) => item.id === value));
}

function HighlightedParent({parent, children}: {parent: string; children: string[]}) {
  const needles = [...new Set(children.map((value) => value.trim()).filter(Boolean))];
  const ranges = needles.map((needle) => ({start: parent.indexOf(needle), length: needle.length})).filter((item) => item.start >= 0).sort((a, b) => a.start - b.start);
  const missing = needles.filter((needle) => !parent.includes(needle));
  if (!ranges.length) return <span>{parent}{missing.map((needle) => <em key={needle} className="mt-2 block rounded bg-amber-400/15 px-2 py-1 text-amber-200">命中子块：{needle}</em>)}</span>;
  const parts = []; let cursor = 0;
  for (const range of ranges) {
    if (range.start < cursor) continue;
    parts.push(parent.slice(cursor, range.start));
    parts.push(<mark key={`${range.start}-${range.length}`} className="rounded bg-amber-300/30 px-0.5 text-amber-100">{parent.slice(range.start, range.start + range.length)}</mark>);
    cursor = range.start + range.length;
  }
  parts.push(parent.slice(cursor));
  return <span>{parts}{missing.map((needle) => <em key={needle} className="mt-2 block rounded bg-amber-400/15 px-2 py-1 text-amber-200">命中子块：{needle}</em>)}</span>;
}

function RagFlowPanel({documents, open, onToggle}: {documents: Array<{text: string; metadata: Record<string, unknown>}>; open: boolean; onToggle: () => void}) {
  if (!documents.length) return null;
  return <div className="overflow-hidden rounded-xl border border-cyan-900/60 bg-slate-900/80"><button className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-cyan-200" onClick={onToggle}>{open ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}Agent 流程 · RAG 检索父块（{documents.length}）</button>{open && <div className="space-y-2 border-t border-cyan-900/50 px-3 py-3">{documents.map((doc) => { const childTexts = Array.isArray(doc.metadata.child_texts) ? doc.metadata.child_texts.filter((value): value is string => typeof value === "string") : typeof doc.metadata.child_text === "string" ? [doc.metadata.child_text] : []; const parentId = String(doc.metadata.parent_id || "?"); return <details key={String(doc.metadata.chunk_id)} className="group rounded-lg border border-slate-800 bg-slate-950/70"><summary className="cursor-pointer list-none px-3 py-2 text-xs text-slate-300"><span className="mr-2 text-cyan-300 group-open:hidden">▸</span><span className="mr-2 hidden text-cyan-300 group-open:inline">▾</span>{String(doc.metadata.filename || "教材")} · 父块 {parentId} · {String(doc.metadata.parent_chars || doc.text.length)} 字符</summary><div className="whitespace-pre-wrap border-t border-slate-800 px-3 py-3 text-xs leading-5 text-slate-300"><HighlightedParent parent={doc.text} children={childTexts}/></div><div className="border-t border-slate-800 px-3 py-2 text-[11px] text-slate-500">黄色高亮为本次向量检索命中的 {String(doc.metadata.matched_child_count || childTexts.length)} 个子块</div></details>; })}</div>}</div>;
}

export default function ChatShell() {
  const [subject, setSubject] = useState("calculus"); const [draft, setDraft] = useState(""); const [showTrace, setShowTrace] = useState(true); const [showSources, setShowSources] = useState(true); const [showSymbols, setShowSymbols] = useState(false); const [fileIds, setFileIds] = useState<string[]>([]); const [modelConfig, setModelConfig] = useState<ModelConfig>({provider: "mock", model: "mock-teacher", temperature: 0.2}); const inputRef = useRef<HTMLTextAreaElement>(null);
  const [indexedSubjectCounts, setIndexedSubjectCounts] = useState<Record<string, number> | null>(null);
  const [subjectReady, setSubjectReady] = useState(false);
  const subjectChangedByUser = useRef(false);
  const {messages, trace, documents, isLoading, error, send, reset, cancel} = useAgenticChat();
  const currentSubject = useMemo(() => subjects.find((item) => item.id === subject)?.label || "微积分", [subject]);
  const currentSubjectHasIndex = indexedSubjectCounts ? (indexedSubjectCounts[subject] || 0) > 0 : null;

  useEffect(() => {
    let active = true;
    const saved = window.localStorage.getItem(subjectStorageKey);
    const savedSubject = isKnownSubject(saved) ? saved : null;
    if (savedSubject) setSubject(savedSubject);

    void listRagIndexes()
      .then((indexes) => {
        if (!active) return;
        const counts: Record<string, number> = {};
        for (const item of indexes) {
          if (isKnownSubject(item.subject) && ["indexed", "processed"].includes(item.status)) {
            counts[item.subject] = (counts[item.subject] || 0) + 1;
          }
        }
        setIndexedSubjectCounts(counts);
        if (!subjectChangedByUser.current) {
          const firstIndexedSubject = subjects.find((item) => (counts[item.id] || 0) > 0)?.id;
          const selected = savedSubject && (counts[savedSubject] || 0) > 0
            ? savedSubject
            : firstIndexedSubject || savedSubject || "calculus";
          setSubject(selected);
          window.localStorage.setItem(subjectStorageKey, selected);
        }
      })
      .catch(() => {
        // Keep the saved subject usable if the index inventory is temporarily
        // unavailable; normal API calls will still surface connection errors.
      })
      .finally(() => { if (active) setSubjectReady(true); });
    return () => { active = false; };
  }, []);

  const changeSubject = (nextSubject: string) => {
    if (!isKnownSubject(nextSubject)) return;
    subjectChangedByUser.current = true;
    window.localStorage.setItem(subjectStorageKey, nextSubject);
    setSubject(nextSubject);
    reset();
  };
  const onDrop = async (files: File[]) => { for (const file of files.slice(0, 4)) { try { const item = await upload(file); setFileIds((ids) => [...ids, item.file_id]); } catch (err) { console.error(err); } } };
  const {getRootProps, getInputProps, isDragActive} = useDropzone({onDrop, accept: {"image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"], "image/webp": [".webp"]}, maxFiles: 4});
  const submit = async (event?: FormEvent) => { event?.preventDefault(); const query = draft.trim(); if (!query || isLoading || !subjectReady) return; setDraft(""); await send(query, subject, fileIds, modelConfig); setFileIds([]); };
  const insertShortcut = (value: string) => { const element = inputRef.current; if (!element) return; const start = element.selectionStart ?? draft.length; const end = element.selectionEnd ?? draft.length; const next = `${draft.slice(0, start)}${value}${draft.slice(end)}`; setDraft(next); requestAnimationFrame(() => { element.focus(); element.setSelectionRange(start + value.length, start + value.length); }); };
  return <main className="min-h-screen bg-slate-950 text-slate-100">
    <div className="mx-auto flex min-h-screen max-w-[1500px]">
      <aside className="hidden w-72 shrink-0 border-r border-slate-800 bg-slate-950/80 p-4 lg:flex lg:flex-col">
        <div className="mb-6 flex items-center gap-2 px-2"><div className="rounded-xl bg-cyan-400/15 p-2 text-cyan-300"><Sparkles size={18}/></div><div><div className="font-semibold">Agentic Teacher</div><div className="text-xs text-slate-500">本地 Agent · 可替换后端</div></div></div>
        <Button className="mb-5 w-full justify-start gap-2" onClick={() => {reset(); setFileIds([]);}}><Plus size={16}/> 新建对话</Button>
        <div className="mb-2 px-2 text-xs uppercase tracking-wider text-slate-500">最近对话</div>
        <div className="space-y-1"><div className="rounded-lg bg-slate-800/70 px-3 py-2 text-sm">欢迎使用理工科导师</div><div className="rounded-lg px-3 py-2 text-sm text-slate-500">历史记录将在本地保存</div></div>
        <div className="mt-auto rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-xs leading-5 text-slate-500"><BookOpen size={15} className="mb-1 text-cyan-300"/>检索来源和执行轨迹仅展示安全摘要，不暴露隐藏思维链。</div>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3 sm:px-8"><div><div className="text-sm text-slate-400">当前学科</div><select value={subject} disabled={!subjectReady} onChange={(e) => changeSubject(e.target.value)} className="mt-1 bg-transparent text-lg font-semibold outline-none disabled:opacity-60"><option className="bg-slate-900" value="calculus">微积分</option><option className="bg-slate-900" value="linear_algebra">线性代数</option><option className="bg-slate-900" value="physics">大学物理</option><option className="bg-slate-900" value="chemistry">化学</option><option className="bg-slate-900" value="programming">C / 算法</option></select></div><div className="flex items-center gap-2"><div className="hidden items-center gap-2 text-xs text-slate-500 sm:flex"><span className="h-2 w-2 rounded-full bg-emerald-400"/>服务就绪 · 本地决策层</div><Link href="/rag" className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:bg-slate-800 hover:text-cyan-300">RAG 管理</Link><ModelSettings value={modelConfig} onChange={setModelConfig}/></div></header>
        {subjectReady && currentSubjectHasIndex === false && <div className="border-b border-amber-900/60 bg-amber-950/30 px-4 py-2 text-center text-xs text-amber-200 sm:px-8">当前学科「{currentSubject}」没有已建立的 RAG 索引；教学资料检索会返回 0 个子块。请切换学科或前往 RAG 管理添加教材。</div>}
        <div className="flex-1 overflow-y-auto px-4 py-8 sm:px-8"><div className="mx-auto max-w-4xl space-y-7">{messages.length === 0 && <div className="py-20 text-center"><div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-400/10 text-cyan-300"><Sparkles size={30}/></div><h1 className="text-3xl font-semibold">你好，我是你的{currentSubject}学习助手</h1><p className="mx-auto mt-3 max-w-xl text-slate-400">可以提问概念、上传手写题目，或直接输入公式。Agent 会在本地编排检索和计算步骤。</p></div>}
          {messages.map((message, index) => <div key={`${index}-${message.role}`} className={message.role === "user" ? "flex justify-end" : "flex justify-start"}><div className={message.role === "user" ? "max-w-[85%] rounded-2xl rounded-br-md bg-cyan-400 px-4 py-3 text-slate-950" : "w-full max-w-[92%]"}>{message.role === "user" ? <div className="whitespace-pre-wrap text-[15px] leading-6">{message.content}</div> : <>{index === messages.length - 1 && <div className="mb-4 space-y-2">{trace.length > 0 && <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70"><button className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-400" onClick={() => setShowTrace(!showTrace)}>{showTrace ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}Agent 执行流程（{trace.length}）</button>{showTrace && <div className="space-y-2 border-t border-slate-800 px-3 py-3">{trace.map((item) => <div key={item.event_id} className="flex gap-2 text-xs"><span className={item.status === "failed" ? "text-rose-400" : "text-cyan-300"}>●</span><span className="text-slate-300">{item.summary || item.step}</span><span className="text-slate-600">{item.status}{typeof item.duration_ms === "number" ? ` · ${item.duration_ms.toFixed(0)} ms` : ""}</span></div>)}</div>}</div>}<RagFlowPanel documents={documents} open={showSources} onToggle={() => setShowSources(!showSources)}/></div>}<MarkdownView content={message.content || (isLoading ? "正在组织答案…" : "")}/></>}</div></div>)}
          {error && <div className="rounded-xl border border-rose-900/80 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">{error}</div>}
        </div></div>
        <form onSubmit={submit} className="border-t border-slate-800 bg-slate-950/95 px-4 py-4 sm:px-8"><div className="mx-auto max-w-4xl"><div {...getRootProps()} className={`mb-3 flex items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs ${isDragActive ? "border-cyan-400 bg-cyan-400/10 text-cyan-300" : "border-slate-800 text-slate-500"}`}><input {...getInputProps()}/><Upload size={14}/>{isDragActive ? "松开以上传图片" : "拖拽或粘贴手写题目图片"}{fileIds.map((fileId) => <span key={fileId} className="rounded bg-slate-800 px-2 py-1 text-cyan-300"><FileImage size={12} className="mr-1 inline"/>{fileId.slice(-6)} <button type="button" onClick={() => setFileIds((ids) => ids.filter((id) => id !== fileId))}><X size={12} className="inline"/></button></span>)}</div><div className="rounded-2xl border border-slate-700 bg-slate-900 p-2 shadow-2xl shadow-cyan-950/10"><textarea ref={inputRef} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => {if (e.key === "Enter" && !e.shiftKey) {e.preventDefault(); void submit();}}} rows={3} placeholder="输入问题，支持 LaTeX：$$f(x)=x^2$$" className="w-full resize-none bg-transparent px-3 py-2 text-[15px] outline-none placeholder:text-slate-600"/><div className="flex items-center justify-between px-2 pb-1"><div className="flex items-center gap-1"><button type="button" className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-cyan-300" onClick={() => setShowSymbols(!showSymbols)} title="公式快捷工具"><Sigma size={17}/></button><button type="button" {...getRootProps()} className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-cyan-300" title="上传图片"><Paperclip size={17}/></button>{showSymbols && <div className="absolute mb-12 flex gap-1 rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-xl">{latexShortcuts.map((item) => <button type="button" key={item} onClick={() => insertShortcut(item)} className="rounded bg-slate-800 px-2 py-1 text-xs text-cyan-200 hover:bg-slate-700">{item}</button>)}</div>}</div>{isLoading ? <Button type="button" variant="secondary" size="icon" onClick={cancel} title="取消"><X size={17}/></Button> : <Button type="submit" size="icon" disabled={!draft.trim() || !subjectReady}><Send size={17}/></Button>}</div></div><div className="mt-2 text-center text-[11px] text-slate-600">Agent 会调用后端模型和检索服务；答案请结合教材核验。</div></div></form>
      </section>
    </div>
  </main>;
}
