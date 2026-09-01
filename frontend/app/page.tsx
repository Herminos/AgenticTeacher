import dynamic from "next/dynamic";

// ChatShell depends on browser-only APIs (drag/drop, streaming and the
// browser-safe LangGraph runtime). Keep those modules out of the server
// prerender bundle so `next build` can generate the route reliably.
const ChatShell = dynamic(() => import("@/components/chat-shell"), {
  ssr: false,
  loading: () => (
    <main className="min-h-screen bg-slate-950 text-slate-100 grid place-items-center">
      <p className="text-slate-400">正在加载 Agentic Teacher…</p>
    </main>
  ),
});

export default function HomePage() {
  return <ChatShell />;
}
