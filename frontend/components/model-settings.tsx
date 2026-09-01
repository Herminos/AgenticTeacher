"use client";

import {useState} from "react";
import {Eye, EyeOff, KeyRound, Save, Settings2} from "lucide-react";
import {Button} from "@/components/ui/button";
import type {ModelConfig, ProviderId} from "@/lib/types";

const PROVIDERS: Array<{id: ProviderId; label: string; base_url: string; model: string; models: string[]}> = [
  {id: "mock", label: "Mock（无需密钥）", base_url: "", model: "mock-teacher", models: ["mock-teacher"]},
  {id: "deepseek", label: "DeepSeek", base_url: "https://api.deepseek.com", model: "deepseek-v4-pro", models: ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"]},
  {id: "qwen", label: "通义千问 Qwen", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen3.8-max", models: ["qwen3.8-max", "qwen3.8-flash", "qwen3.7-plus"]},
  {id: "openai", label: "OpenAI / ChatGPT", base_url: "https://api.openai.com/v1", model: "gpt-5.6-sol", models: ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"]},
];

const initial: ModelConfig = {provider: "mock", base_url: "", model: "mock-teacher", api_key: "", temperature: 0.2};

export function ModelSettings({value = initial, onChange}: {value?: ModelConfig; onChange: (next: ModelConfig) => void}) {
  const [open, setOpen] = useState(false);
  const [visible, setVisible] = useState(false);
  const selected = PROVIDERS.find((item) => item.id === value.provider) || PROVIDERS[0];
  const modelValue = selected.models.includes(value.model || "") ? value.model || selected.model : selected.model;
  const update = (patch: Partial<ModelConfig>) => onChange({...value, ...patch});
  const selectProvider = (provider: ProviderId) => {
    const defaults = PROVIDERS.find((item) => item.id === provider) || PROVIDERS[0];
    update({provider, base_url: defaults.base_url, model: defaults.model, api_key: provider === "mock" ? "" : value.api_key});
  };
  return <div className="relative">
    <Button type="button" variant="ghost" size="sm" className="gap-2 text-slate-400" onClick={() => setOpen((current) => !current)}><Settings2 size={16}/>模型设置</Button>
    {open && <div className="absolute right-0 top-10 z-30 w-[min(92vw,390px)] rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between"><div className="flex items-center gap-2 text-sm font-medium"><KeyRound size={15} className="text-cyan-300"/>模型 API</div><button type="button" className="text-xs text-cyan-300" onClick={() => {onChange({...initial}); setOpen(false);}}>恢复 Mock</button></div>
      <label className="mb-3 block text-xs text-slate-400">模型提供商<select value={value.provider} onChange={(event) => selectProvider(event.target.value as ProviderId)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none"><option value="mock">Mock（无需密钥）</option>{PROVIDERS.slice(1).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <label className="mb-3 block text-xs text-slate-400">Base URL<span className="ml-1 text-slate-600">（可改为代理地址）</span><input value={value.base_url || ""} onChange={(event) => update({base_url: event.target.value})} placeholder={selected.base_url || "无需填写"} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none" /></label>
      <label className="mb-3 block text-xs text-slate-400">模型名称<select value={modelValue} onChange={(event) => update({model: event.target.value})} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none">{selected.models.map((model) => <option key={model} value={model}>{model}</option>)}</select></label>
      {value.provider !== "mock" && <label className="mb-3 block text-xs text-slate-400">个人 API Key / SK<input type={visible ? "text" : "password"} value={value.api_key || ""} onChange={(event) => update({api_key: event.target.value})} placeholder="仅保存在当前页面内存" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 pr-9 text-sm text-slate-100 outline-none" /> <button type="button" aria-label={visible ? "隐藏密钥" : "显示密钥"} onClick={() => setVisible((current) => !current)} className="relative float-right -mt-8 mr-2 text-slate-500">{visible ? <EyeOff size={15}/> : <Eye size={15}/>}</button></label>}
      <label className="mb-3 block text-xs text-slate-400">Temperature <span className="text-slate-500">{(value.temperature ?? 0.2).toFixed(1)}</span><input type="range" min="0" max="2" step="0.1" value={value.temperature ?? 0.2} onChange={(event) => update({temperature: Number(event.target.value)})} className="mt-2 w-full accent-cyan-400" /></label>
      <div className="mb-3 rounded-lg bg-amber-950/30 px-3 py-2 text-[11px] leading-5 text-amber-200/80">密钥仅随当前请求发送到你的后端，不会写入浏览器持久化存储。生产环境请启用 HTTPS 和服务端鉴权。</div>
      <Button type="button" size="sm" className="w-full gap-2" onClick={() => setOpen(false)}><Save size={14}/>保存本次会话设置</Button>
    </div>}
  </div>;
}
