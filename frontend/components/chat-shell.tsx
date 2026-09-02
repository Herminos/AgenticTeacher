"use client";

import React, {FormEvent, useMemo, useRef, useState} from "react";
import {useDropzone} from "react-dropzone";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import {Prism as SyntaxHighlighter} from "react-syntax-highlighter";
import {oneDark} from "react-syntax-highlighter/dist/esm/styles/prism";
import {BookOpen, ChevronDown, ChevronRight, FileImage, Loader2, Paperclip, Plus, Send, Sigma, Sparkles, Upload, X} from "lucide-react";
import {Button} from "@/components/ui/button";
import {upload} from "@/lib/api";
import {useAgenticChat} from "@/hooks/useAgenticChat";
import {ModelSettings} from "@/components/model-settings";
import {RagIndexPanel} from "@/components/rag-index-panel";
import type {ModelConfig} from "@/lib/types";

class MarkdownBoundary extends React.Component<{children: React.ReactNode; fallback: string}, {failed: boolean}> {
  state = {failed: false};
  static getDerivedStateFromError() { return {failed: true}; }
  render() { return this.state.failed ? <pre className="whitespace-pre-wrap text-sm text-slate-300">{this.props.fallback}</pre> : this.props.children; }
}

function MarkdownView({content}: {content: string}) {
  return <MarkdownBoundary fallback={content}><div className="prose prose-invert max-w-none text-[15px] leading-7"><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]} components={{code({className, children, ...props}) { const match = /language-(\w+)/.exec(className || ""); return match ? <SyntaxHighlighter style={oneDark} language={match[1]} PreTag="div">{String(children).replace(/\n$/, "")}</SyntaxHighlighter> : <code className="rounded bg-slate-800 px-1 py-0.5" {...props}>{children}</code>; }}}>{content}</ReactMarkdown></div></MarkdownBoundary>;
}

const subjects = [{id: "calculus", label: "微积分"}, {id: "linear_algebra", label: "线性代数"}, {id: "physics", label: "大学物理"}, {id: "chemistry", label: "化学"}, {id: "programming", label: "C / 算法"}];
const latexShortcuts = ["\\frac{}{}", "\\int", "\\sum", "\\alpha", "\\beta", "\\partial"];

export default function ChatShell() {
  const [subject, setSubject] = useState("calculus"); const [draft, setDraft] = useState(""); const [showTrace, setShowTrace] = useState(true); const [showSources, setShowSources] = useState(true); const [showSymbols, setShowSymbols] = useState(false); const [showIndexer, setShowIndexer] = useState(false); const [fileIds, setFileIds] = useState<string[]>([]); const [modelConfig, setModelConfig] = useState<ModelConfig>({provider: "mock", model: "mock-teacher", temperature: 0.2}); const inputRef = useRef<HTMLTextAreaElement>(null);
  const {messages, trace, documents, isLoading, error, send, reset, cancel} = useAgenticChat();
  const currentSubject = useMemo(() => subjects.find((item) => item.id === subject)?.label || "微积分", [subject]);
  const onDrop = async (files: File[]) => { for (const file of files.slice(0, 4)) { try { const item = await upload(file); setFileIds((ids) => [...ids, item.file_id]); } catch (err) { console.error(err); } } };
  const {getRootProps, getInputProps, isDragActive} = useDropzone({onDrop, accept: {"image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"], "image/webp": [".webp"]}, maxFiles: 4});
  const submit = async (event?: FormEvent) => { event?.preventDefault(); const query = draft.trim(); if (!query || isLoading) return; setDraft(""); await send(query, subject, fileIds, modelConfig); setFileIds([]); };
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
        <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3 sm:px-8"><div><div className="text-sm text-slate-400">当前学科</div><select value={subject} onChange={(e) => {setSubject(e.target.value); reset(); setShowIndexer(false);}} className="mt-1 bg-transparent text-lg font-semibold outline-none"><option className="bg-slate-900" value="calculus">微积分</option><option className="bg-slate-900" value="linear_algebra">线性代数</option><option className="bg-slate-900" value="physics">大学物理</option><option className="bg-slate-900" value="chemistry">化学</option><option className="bg-slate-900" value="programming">C / 算法</option></select></div><div className="flex items-center gap-2"><div className="hidden items-center gap-2 text-xs text-slate-500 sm:flex"><span className="h-2 w-2 rounded-full bg-emerald-400"/>服务就绪 · 本地决策层</div><Button type="button" variant="ghost" className="gap-1.5 text-xs text-slate-400 hover:text-cyan-300" onClick={() => setShowIndexer((value) => !value)}><Upload size={15}/>RAG Index</Button><ModelSettings value={modelConfig} onChange={setModelConfig}/></div></header>
        {showIndexer && <RagIndexPanel subject={subject} subjectLabel={currentSubject} onClose={() => setShowIndexer(false)}/>} 
        <div className="flex-1 overflow-y-auto px-4 py-8 sm:px-8"><div className="mx-auto max-w-4xl space-y-7">{messages.length === 0 && <div className="py-20 text-center"><div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-400/10 text-cyan-300"><Sparkles size={30}/></div><h1 className="text-3xl font-semibold">你好，我是你的{currentSubject}学习助手</h1><p className="mx-auto mt-3 max-w-xl text-slate-400">可以提问概念、上传手写题目，或直接输入公式。Agent 会在本地编排检索和计算步骤。</p></div>}
          {messages.map((message, index) => <div key={`${index}-${message.role}`} className={message.role === "user" ? "flex justify-end" : "flex justify-start"}><div className={message.role === "user" ? "max-w-[85%] rounded-2xl rounded-br-md bg-cyan-400 px-4 py-3 text-slate-950" : "w-full max-w-[92%]"}>{message.role === "user" ? <div className="whitespace-pre-wrap text-[15px] leading-6">{message.content}</div> : <><MarkdownView content={message.content || (isLoading ? "正在组织答案…" : "")}/>{index === messages.length - 1 && <div className="mt-4 space-y-2">{trace.length > 0 && <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70"><button className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-400" onClick={() => setShowTrace(!showTrace)}>{showTrace ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}执行轨迹（{trace.length}）</button>{showTrace && <div className="space-y-2 border-t border-slate-800 px-3 py-3">{trace.map((item) => <div key={item.event_id} className="flex gap-2 text-xs"><span className={item.status === "failed" ? "text-rose-400" : "text-cyan-300"}>●</span><span className="text-slate-300">{item.summary || item.step}</span><span className="text-slate-600">{item.status}{typeof item.duration_ms === "number" ? ` · ${item.duration_ms.toFixed(0)} ms` : ""}</span></div>)}</div>}</div>}{documents.length > 0 && <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70"><button className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-400" onClick={() => setShowSources(!showSources)}>{showSources ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}参考来源（{documents.length}）</button>{showSources && <div className="space-y-2 border-t border-slate-800 px-3 py-3">{documents.map((doc) => <div key={doc.metadata.chunk_id} className="rounded-lg bg-slate-950/70 p-3 text-xs"><div className="mb-1 flex items-center gap-2 text-cyan-300"><BookOpen size={13}/>{String(doc.metadata.filename || "教材")} · p.{String(doc.metadata.page || "?")}</div><div className="text-slate-400">{doc.text}</div></div>)}</div>}</div>}</div>}</>}</div></div>)}
          {error && <div className="rounded-xl border border-rose-900/80 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">{error}</div>}
        </div></div>
        <form onSubmit={submit} className="border-t border-slate-800 bg-slate-950/95 px-4 py-4 sm:px-8"><div className="mx-auto max-w-4xl"><div {...getRootProps()} className={`mb-3 flex items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs ${isDragActive ? "border-cyan-400 bg-cyan-400/10 text-cyan-300" : "border-slate-800 text-slate-500"}`}><input {...getInputProps()}/><Upload size={14}/>{isDragActive ? "松开以上传图片" : "拖拽或粘贴手写题目图片"}{fileIds.map((fileId) => <span key={fileId} className="rounded bg-slate-800 px-2 py-1 text-cyan-300"><FileImage size={12} className="mr-1 inline"/>{fileId.slice(-6)} <button type="button" onClick={() => setFileIds((ids) => ids.filter((id) => id !== fileId))}><X size={12} className="inline"/></button></span>)}</div><div className="rounded-2xl border border-slate-700 bg-slate-900 p-2 shadow-2xl shadow-cyan-950/10"><textarea ref={inputRef} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => {if (e.key === "Enter" && !e.shiftKey) {e.preventDefault(); void submit();}}} rows={3} placeholder="输入问题，支持 LaTeX：$$f(x)=x^2$$" className="w-full resize-none bg-transparent px-3 py-2 text-[15px] outline-none placeholder:text-slate-600"/><div className="flex items-center justify-between px-2 pb-1"><div className="flex items-center gap-1"><button type="button" className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-cyan-300" onClick={() => setShowSymbols(!showSymbols)} title="公式快捷工具"><Sigma size={17}/></button><button type="button" {...getRootProps()} className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-cyan-300" title="上传图片"><Paperclip size={17}/></button>{showSymbols && <div className="absolute mb-12 flex gap-1 rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-xl">{latexShortcuts.map((item) => <button type="button" key={item} onClick={() => insertShortcut(item)} className="rounded bg-slate-800 px-2 py-1 text-xs text-cyan-200 hover:bg-slate-700">{item}</button>)}</div>}</div>{isLoading ? <Button type="button" variant="secondary" size="icon" onClick={cancel} title="取消"><X size={17}/></Button> : <Button type="submit" size="icon" disabled={!draft.trim()}><Send size={17}/></Button>}</div></div><div className="mt-2 text-center text-[11px] text-slate-600">Agent 会调用后端模型和检索服务；答案请结合教材核验。</div></div></form>
      </section>
    </div>
  </main>;
}
