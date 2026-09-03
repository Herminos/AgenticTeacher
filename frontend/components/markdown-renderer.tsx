"use client";

import React from "react";
import ReactMarkdown, {type Components} from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import {Prism as SyntaxHighlighter} from "react-syntax-highlighter";
import {oneDark} from "react-syntax-highlighter/dist/esm/styles/prism";

type MarkdownRendererProps = {content: string; compact?: boolean};

/** Convert the other common TeX delimiters to remark-math's $ delimiters. */
function normalizeMath(source: string): string {
  // Do not rewrite delimiters inside fenced code examples.
  return source.split(/(```[\s\S]*?```)/g).map((segment, index) => {
    if (index % 2 === 1) return segment;
    return segment
      .replace(/\\\[([\s\S]*?)\\\]/g, (_, expression: string) => `$$${expression}$$`)
      .replace(/\\\(([\s\S]*?)\\\)/g, (_, expression: string) => `$${expression}$`);
  }).join("");
}

function safeHref(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value, "https://agentic-teacher.invalid");
    if (["http:", "https:", "mailto:"].includes(url.protocol)) return value;
  } catch { /* malformed links are rendered as text */ }
  return undefined;
}

class MarkdownErrorBoundary extends React.Component<
  {children: React.ReactNode; fallback: string},
  {failed: boolean}
> {
  state = {failed: false};

  static getDerivedStateFromError() {
    return {failed: true};
  }

  render() {
    if (this.state.failed) {
      return <pre className="whitespace-pre-wrap break-words text-[15px] leading-7 text-slate-300">{this.props.fallback}</pre>;
    }
    return this.props.children;
  }
}

const components: Components = {
  h1: ({children}) => <h1 className="mb-4 mt-6 text-2xl font-semibold text-slate-100 first:mt-0">{children}</h1>,
  h2: ({children}) => <h2 className="mb-3 mt-5 text-xl font-semibold text-slate-100">{children}</h2>,
  h3: ({children}) => <h3 className="mb-2 mt-4 text-lg font-semibold text-slate-100">{children}</h3>,
  h4: ({children}) => <h4 className="mb-2 mt-4 font-semibold text-slate-100">{children}</h4>,
  p: ({children}) => <p className="my-3 leading-7 text-slate-200 first:mt-0 last:mb-0">{children}</p>,
  ul: ({children}) => <ul className="my-3 list-disc space-y-1 pl-6 text-slate-200">{children}</ul>,
  ol: ({children}) => <ol className="my-3 list-decimal space-y-1 pl-6 text-slate-200">{children}</ol>,
  li: ({children}) => <li className="pl-1 leading-7">{children}</li>,
  blockquote: ({children}) => <blockquote className="my-4 border-l-2 border-cyan-400/70 bg-cyan-950/20 px-4 py-1 text-slate-300">{children}</blockquote>,
  hr: () => <hr className="my-6 border-slate-700" />,
  strong: ({children}) => <strong className="font-semibold text-slate-100">{children}</strong>,
  em: ({children}) => <em className="text-slate-300">{children}</em>,
  del: ({children}) => <del className="text-slate-500">{children}</del>,
  a: ({href, children}) => {
    const safe = safeHref(href);
    return safe ? <a href={safe} target="_blank" rel="noreferrer noopener" className="text-cyan-300 underline decoration-cyan-500/50 underline-offset-2 hover:text-cyan-200">{children}</a> : <span>{children}</span>;
  },
  img: ({src, alt}) => {
    const safe = src?.startsWith("data:image/") || src?.startsWith("https://") || src?.startsWith("http://") ? src : undefined;
    return safe ? <img src={safe} alt={alt || ""} loading="lazy" className="my-4 max-h-[480px] max-w-full rounded-lg border border-slate-700 object-contain" /> : <span className="text-slate-500">{alt || "[图片已过滤]"}</span>;
  },
  table: ({children}) => <div className="my-4 overflow-x-auto rounded-lg border border-slate-700"><table className="min-w-full border-collapse text-sm">{children}</table></div>,
  thead: ({children}) => <thead className="bg-slate-800/80 text-slate-100">{children}</thead>,
  th: ({children}) => <th className="border-b border-slate-700 px-3 py-2 text-left font-semibold">{children}</th>,
  td: ({children}) => <td className="border-b border-slate-800 px-3 py-2 align-top text-slate-300">{children}</td>,
  code: ({className, children, ...props}) => {
    const language = /language-([\w+-]+)/.exec(className || "")?.[1];
    const code = String(children).replace(/\n$/, "");
    if (!language) return <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[0.9em] text-cyan-200" {...props}>{children}</code>;
    return <div className="my-4 overflow-hidden rounded-xl border border-slate-700"><div className="border-b border-slate-700 bg-slate-800/80 px-3 py-1.5 text-[11px] text-slate-400">{language}</div><SyntaxHighlighter style={oneDark} language={language} PreTag="div" customStyle={{margin: 0, borderRadius: 0, background: "#020617", fontSize: "0.85rem"}}>{code}</SyntaxHighlighter></div>;
  },
};

export function MarkdownRenderer({content, compact = false}: MarkdownRendererProps) {
  const source = normalizeMath(content);
  return <MarkdownErrorBoundary fallback={content}><div className={compact ? "markdown-body markdown-compact" : "markdown-body"}><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, {throwOnError: false, strict: "ignore", trust: false}]]} components={components}>{source}</ReactMarkdown></div></MarkdownErrorBoundary>;
}
