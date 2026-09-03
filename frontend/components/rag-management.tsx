"use client";

import {useEffect, useRef, useState} from "react";
import Link from "next/link";
import {ArrowLeft, BookOpen, Eye, FilePlus2, FolderOpen, Loader2, RefreshCw, Save, Trash2, X} from "lucide-react";
import {Button} from "@/components/ui/button";
import {deleteRagChunk, deleteRagIndex, getRagIndex, getRagSettings, indexFiles, listRagIndexes, updateRagSettings, type RagChunk, type RagDetail, type RagFile, type RagSettings} from "@/lib/api";

const subjects = [{id: "calculus", label: "微积分"}, {id: "linear_algebra", label: "线性代数"}, {id: "physics", label: "大学物理"}, {id: "chemistry", label: "化学"}, {id: "programming", label: "C / 算法"}];
const accepted = ".pdf,.pptx,.txt,.md,.markdown";

function size(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function SettingInput({label, value, onChange, min, max}: {label: string; value: number; onChange: (value: number) => void; min: number; max: number}) {
  return <label className="space-y-1 text-xs text-slate-400"><span>{label}</span><input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"/></label>;
}

export function RagManagement() {
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const [subject, setSubject] = useState("calculus");
  const [settings, setSettings] = useState<RagSettings>({chunk_chars: 512, retrieval_top_k: 16, reranker_top_k: 4});
  const [files, setFiles] = useState<RagFile[]>([]);
  const [detail, setDetail] = useState<RagDetail | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    try {
      const [nextSettings, nextFiles] = await Promise.all([getRagSettings(), listRagIndexes(subject)]);
      setSettings(nextSettings);
      setFiles(nextFiles);
      setNotice("");
    } catch (error) { setNotice(error instanceof Error ? error.message : "无法读取 RAG 数据"); }
    finally { setLoading(false); }
  };

  useEffect(() => { void refresh(); }, [subject]);

  const saveSettings = async () => {
    setBusy(true);
    try { setSettings(await updateRagSettings(settings)); setNotice("RAG 参数已保存"); }
    catch (error) { setNotice(error instanceof Error ? error.message : "保存 RAG 参数失败"); }
    finally { setBusy(false); }
  };

  const indexSelected = async (list: FileList | null) => {
    if (!list || !list.length) return;
    setBusy(true);
    try {
      const selected = Array.from(list);
      const result = await indexFiles(selected, subject, 0, {chunkChars: settings.chunk_chars, retrievalTopK: settings.retrieval_top_k, rerankerTopK: settings.reranker_top_k});
      setNotice(`索引完成：${result.files_indexed} 个文件，${result.chunks} 个 Chunk，新增 ${result.added_chunks} 个`);
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : "RAG Index 失败"); }
    finally { setBusy(false); if (fileInput.current) fileInput.current.value = ""; }
  };

  const openDetail = async (file: RagFile) => {
    setBusy(true);
    try { setDetail(await getRagIndex(file.file_id)); }
    catch (error) { setNotice(error instanceof Error ? error.message : "无法读取文件详情"); }
    finally { setBusy(false); }
  };

  const removeFile = async (file: RagFile) => {
    if (!window.confirm(`确定删除「${file.filename}」及其全部 ${file.chunks} 个 Chunk 吗？`)) return;
    setBusy(true);
    try { await deleteRagIndex(file.file_id); if (detail?.file_id === file.file_id) setDetail(null); setNotice(`已删除 ${file.filename}`); await refresh(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "删除文件失败"); }
    finally { setBusy(false); }
  };

  const removeChunk = async (chunk: RagChunk) => {
    if (!detail || !window.confirm("确定删除这个 Chunk 吗？")) return;
    setBusy(true);
    try { await deleteRagChunk(detail.file_id, chunk.chunk_id); setDetail(await getRagIndex(detail.file_id, detail.chunk_offset, detail.chunk_limit)); setFiles((items) => items.map((item) => item.file_id === detail.file_id ? {...item, chunks: Math.max(0, item.chunks - 1)} : item)); }
    catch (error) { setNotice(error instanceof Error ? error.message : "删除 Chunk 失败"); }
    finally { setBusy(false); }
  };

  const subjectLabel = subjects.find((item) => item.id === subject)?.label || subject;
  return <main className="min-h-screen bg-slate-950 text-slate-100"><header className="border-b border-slate-800"><div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-8"><div className="flex items-center gap-3"><Link href="/" className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-cyan-300" aria-label="返回对话"><ArrowLeft size={18}/></Link><div><div className="flex items-center gap-2 text-lg font-semibold"><BookOpen size={19} className="text-cyan-300"/>RAG 管理</div><div className="text-xs text-slate-500">按文件隔离的索引、Chunk 和检索参数</div></div></div><div className="flex items-center gap-2"><select value={subject} onChange={(event) => {setSubject(event.target.value); setDetail(null);}} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"><option value="calculus">微积分</option><option value="linear_algebra">线性代数</option><option value="physics">大学物理</option><option value="chemistry">化学</option><option value="programming">C / 算法</option></select><Button type="button" variant="ghost" size="icon" onClick={() => void refresh()} disabled={loading || busy} title="刷新"><RefreshCw size={16} className={loading ? "animate-spin" : ""}/></Button></div></div></header>
    <div className="mx-auto grid max-w-6xl gap-5 px-4 py-6 sm:px-8 lg:grid-cols-[280px_1fr]"><aside className="space-y-4"><section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4"><h2 className="text-sm font-semibold">RAG 参数</h2><p className="mt-1 text-xs leading-5 text-slate-500">新建索引和对话检索使用以下服务端配置。</p><div className="mt-4 space-y-3"><SettingInput label="Chunk 字符数" value={settings.chunk_chars} min={128} max={8192} onChange={(value) => setSettings({...settings, chunk_chars: value})}/><SettingInput label="召回 TopK" value={settings.retrieval_top_k} min={1} max={64} onChange={(value) => setSettings({...settings, retrieval_top_k: value})}/><SettingInput label="Reranker 最终 TopK" value={settings.reranker_top_k} min={1} max={32} onChange={(value) => setSettings({...settings, reranker_top_k: value})}/><Button type="button" className="w-full gap-2" onClick={() => void saveSettings()} disabled={busy}><Save size={15}/>保存参数</Button></div></section><section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4"><h2 className="text-sm font-semibold">添加教材</h2><p className="mt-1 text-xs leading-5 text-slate-500">服务端解析 PDF、PPTX、TXT 和 Markdown，并写入独立文件 Collection。</p><input ref={fileInput} type="file" multiple accept={accepted} className="hidden" onChange={(event) => void indexSelected(event.target.files)}/><input ref={folderInput} type="file" multiple className="hidden" {...({webkitdirectory: ""} as Record<string, string>)} onChange={(event) => void indexSelected(event.target.files)}/><div className="mt-3 grid grid-cols-2 gap-2"><Button type="button" variant="secondary" className="gap-2" onClick={() => fileInput.current?.click()} disabled={busy}><FilePlus2 size={15}/>选择文件</Button><Button type="button" variant="secondary" className="gap-2" onClick={() => folderInput.current?.click()} disabled={busy}><FolderOpen size={15}/>选择目录</Button></div></section>{notice && <div className="rounded-xl border border-cyan-900/60 bg-cyan-950/30 px-3 py-2 text-xs leading-5 text-cyan-200">{notice}</div>}</aside><section className="min-w-0"><div className="mb-3 flex items-center justify-between"><div><h1 className="text-xl font-semibold">{subjectLabel} · 文件索引</h1><p className="mt-1 text-xs text-slate-500">共 {files.length} 个文件；每个文件拥有独立 Collection，可单独删除。</p></div>{busy && <Loader2 size={17} className="animate-spin text-cyan-300"/>}</div>{files.length === 0 && !loading ? <div className="rounded-2xl border border-dashed border-slate-700 px-6 py-16 text-center text-sm text-slate-500">当前学科还没有 RAG 文件索引。</div> : <div className="space-y-3">{files.map((file) => <article key={file.file_id} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4"><div className="flex items-start justify-between gap-4"><div className="min-w-0"><h2 className="truncate text-sm font-medium text-slate-100">{file.filename}</h2><div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500"><span>{size(file.size_bytes)}</span><span>{file.chunks} Chunks</span><span>Chunk {file.chunk_chars} 字符</span><span>{file.embedding_model}</span></div><div className="mt-1 truncate text-[11px] text-slate-600">{file.collection} · {file.file_id}</div></div><div className="flex shrink-0 gap-1"><Button type="button" variant="ghost" size="icon" onClick={() => void openDetail(file)} title="查看 Chunk"><Eye size={16}/></Button><Button type="button" variant="ghost" size="icon" className="text-rose-300 hover:text-rose-200" onClick={() => void removeFile(file)} title="删除文件"><Trash2 size={16}/></Button></div></div></article>)}</div>}{detail && <div className="fixed inset-0 z-20 bg-slate-950/80 p-4 backdrop-blur-sm sm:p-8"><div className="mx-auto flex h-full max-w-5xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"><div className="flex items-start justify-between border-b border-slate-800 p-4"><div className="min-w-0"><h2 className="truncate font-semibold">{detail.filename}</h2><div className="mt-1 text-xs text-slate-500">{detail.file_id} · {detail.collection} · SHA256 {detail.content_hash}</div><div className="mt-1 text-xs text-slate-400">解析器 {detail.parser_version} · Embedding {detail.embedding_model}</div></div><button type="button" onClick={() => setDetail(null)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-800" aria-label="关闭"><X size={18}/></button></div><div className="flex-1 overflow-y-auto p-4"><div className="mb-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-3"><div>Chunk 字符数：{detail.chunk_chars}</div><div>召回 TopK：{detail.retrieval_top_k}</div><div>Reranker TopK：{detail.reranker_top_k}</div></div><div className="space-y-3">{detail.chunk_items.map((chunk) => <div key={chunk.chunk_id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-3"><div className="flex items-start justify-between gap-3"><div className="text-[11px] text-cyan-300">#{chunk.chunk_index ?? "?"} · {chunk.chunk_id} · p.{chunk.page ?? "?"} · {chunk.chapter || "未分类"}</div><Button type="button" variant="ghost" size="icon" className="h-7 w-7 text-rose-300" onClick={() => void removeChunk(chunk)} title="删除 Chunk"><Trash2 size={14}/></Button></div><p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">{chunk.text}</p><div className="mt-2 text-[10px] text-slate-600">content_hash: {chunk.content_hash} · parser: {chunk.parser_version}</div></div>)}{detail.chunk_items.length === 0 && <div className="py-10 text-center text-sm text-slate-500">没有可显示的 Chunk。</div>}</div></div></div></div>}</section></div></main>;
}
