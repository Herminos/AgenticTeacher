"use client";

import {useRef, useState} from "react";
import {AlertCircle, CheckCircle2, FileText, FolderOpen, Loader2, UploadCloud, X} from "lucide-react";
import {indexFiles, type IndexResult} from "@/lib/api";
import {Button} from "@/components/ui/button";

const ACCEPTED_EXTENSIONS = new Set([".pdf", ".pptx", ".txt", ".md", ".markdown"]);
const MAX_FILES = 100;
const MAX_FILE_BYTES = 10 * 1024 * 1024 * 1024;
const MAX_TOTAL_BYTES = 10 * 1024 * 1024 * 1024;

function extension(name: string) {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

function displaySize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

interface RagIndexPanelProps {
  subject: string;
  subjectLabel: string;
  onClose: () => void;
}

export function RagIndexPanel({subject, subjectLabel, onClose}: RagIndexPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const directoryInputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [notice, setNotice] = useState("");
  const [result, setResult] = useState<IndexResult | null>(null);
  const [isIndexing, setIsIndexing] = useState(false);

  const selectFiles = (list: FileList | null) => {
    if (!list) return;
    const incoming = Array.from(list);
    const unsupported = incoming.filter((file) => !ACCEPTED_EXTENSIONS.has(extension(file.name)));
    const accepted = incoming.filter((file) => ACCEPTED_EXTENSIONS.has(extension(file.name))).slice(0, MAX_FILES);
    const oversized = accepted.filter((file) => file.size > MAX_FILE_BYTES);
    if (oversized.length > 0) {
      setFiles([]);
      setResult(null);
      setNotice(`单个文件不能超过 10 GB：${oversized[0].name}`);
      return;
    }
    const total = accepted.reduce((sum, file) => sum + file.size, 0);
    if (unsupported.length > 0) setNotice(`已跳过 ${unsupported.length} 个不支持的文件，仅支持 PDF、PPTX、TXT 和 Markdown。`);
    else if (incoming.length > MAX_FILES) setNotice(`最多选择 ${MAX_FILES} 个文件，超出部分已跳过。`);
    else setNotice("");
    if (total > MAX_TOTAL_BYTES) {
      setFiles([]);
      setNotice("所选文件总大小超过 10 GB，请分批建立索引。");
      return;
    }
    setFiles(accepted);
    setResult(null);
  };

  const startIndex = async () => {
    if (!files.length || isIndexing) return;
    setIsIndexing(true);
    setResult(null);
    try {
      setResult(await indexFiles(files, subject));
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "RAG Index 失败，请重试。");
    } finally {
      setIsIndexing(false);
    }
  };

  return (
    <section className="border-b border-slate-800 bg-slate-900/50 px-4 py-4 sm:px-8">
      <div className="mx-auto max-w-4xl rounded-2xl border border-cyan-400/20 bg-slate-900 p-4 shadow-xl shadow-cyan-950/10">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-base font-semibold text-slate-100"><UploadCloud size={18} className="text-cyan-300"/> RAG Index</div>
            <p className="mt-1 text-xs leading-5 text-slate-400">为「{subjectLabel}」建立教材索引。浏览器只上传文件，解析、分块、嵌入和 Qdrant 写入全部由服务端完成。</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200" aria-label="关闭 RAG Index"><X size={17}/></button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <input ref={fileInputRef} type="file" multiple accept=".pdf,.pptx,.txt,.md,.markdown" className="hidden" onChange={(event) => {selectFiles(event.target.files); event.currentTarget.value = "";}} />
          <input ref={directoryInputRef} type="file" multiple className="hidden" {...({webkitdirectory: ""} as Record<string, string>)} onChange={(event) => {selectFiles(event.target.files); event.currentTarget.value = "";}} />
          <Button type="button" variant="secondary" onClick={() => fileInputRef.current?.click()}><FileText size={15}/>选择文件</Button>
          <Button type="button" variant="secondary" onClick={() => directoryInputRef.current?.click()}><FolderOpen size={15}/>选择目录</Button>
          <Button type="button" onClick={() => void startIndex()} disabled={!files.length || isIndexing}><>{isIndexing ? <Loader2 size={15} className="animate-spin"/> : <UploadCloud size={15}/>}</> {isIndexing ? "正在建立索引…" : "开始 RAG Index"}</Button>
        </div>
        {files.length > 0 && <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3"><div className="mb-2 text-xs text-slate-400">已选择 {files.length} 个文件 · {displaySize(files.reduce((sum, file) => sum + file.size, 0))}</div><div className="max-h-28 space-y-1 overflow-y-auto">{files.map((file) => <div key={`${file.name}-${file.size}-${file.lastModified}`} className="truncate text-xs text-slate-300">{(file as File & {webkitRelativePath?: string}).webkitRelativePath || file.name}</div>)}</div></div>}
        {notice && <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-xs text-amber-200"><AlertCircle size={14} className="mt-0.5 shrink-0"/>{notice}</div>}
        {result && <div className="mt-3 rounded-xl border border-emerald-900/60 bg-emerald-950/20 p-3 text-sm"><div className="flex items-center gap-2 font-medium text-emerald-200"><CheckCircle2 size={16}/>索引建立完成</div><div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-300 sm:grid-cols-4"><div>文件：{result.files_indexed}/{result.files_received}</div><div>Chunks：{result.chunks}</div><div>新增：{result.added_chunks}</div><div>耗时：{result.duration_ms.toFixed(0)} ms</div></div><div className="mt-2 text-[11px] text-slate-500">Collection：{result.collection} · Embedding：{result.embedding_model} · Index ID：{result.index_id}</div></div>}
      </div>
    </section>
  );
}
