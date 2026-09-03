import dynamic from "next/dynamic";

const RagManagement = dynamic(() => import("@/components/rag-management").then((module) => module.RagManagement), {
  ssr: false,
  loading: () => <main className="grid min-h-screen place-items-center bg-slate-950 text-slate-400">正在加载 RAG 管理…</main>,
});

export default function RagPage() {
  return <RagManagement />;
}
