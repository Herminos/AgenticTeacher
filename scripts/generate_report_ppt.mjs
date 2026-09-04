import pptxgen from "/tmp/agenticteacher-ppt/node_modules/pptxgenjs/dist/pptxgen.cjs.js";

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "AgenticTeacher";
pptx.subject = "Agentic RAG 智能教学系统项目汇报";
pptx.title = "AgenticTeacher 项目汇报";
pptx.company = "AgenticTeacher";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Noto Sans CJK SC",
  bodyFontFace: "Noto Sans CJK SC",
  lang: "zh-CN",
};
pptx.defineSlideMaster({
  title: "MASTER",
  background: {color: "08111F"},
  objects: [
    {line: {x: 0.55, y: 7.12, w: 12.22, h: 0, line: {color: "203047", width: 0.7}}},
    {text: {text: "AgenticTeacher · 本地 Agent / 服务端 RAG", options: {x: 0.62, y: 7.18, w: 5.4, h: 0.18, fontFace: "Noto Sans CJK SC", fontSize: 7.5, color: "69809D", margin: 0}}},
  ],
  slideNumber: {x: 12.35, y: 7.16, w: 0.35, h: 0.2, fontFace: "Noto Sans CJK SC", fontSize: 8, color: "69809D", align: "right", margin: 0},
});

const C = {
  bg: "08111F", panel: "101D2E", panel2: "13253A", stroke: "29415E",
  white: "F4F8FC", text: "CAD7E6", muted: "8295AD", cyan: "35D0E5",
  blue: "4C8DFF", amber: "FFB84D", green: "54D6A0", red: "FF6B7D",
};
const FONT = "Noto Sans CJK SC";

function addTitle(slide, kicker, title, subtitle = "") {
  slide.addText(kicker.toUpperCase(), {x: 0.66, y: 0.42, w: 4.0, h: 0.22, fontFace: FONT, fontSize: 9, bold: true, color: C.cyan, charSpacing: 1.6, margin: 0});
  slide.addText(title, {x: 0.64, y: 0.73, w: 11.9, h: 0.54, fontFace: FONT, fontSize: 25, bold: true, color: C.white, margin: 0, breakLine: false, fit: "shrink"});
  if (subtitle) slide.addText(subtitle, {x: 0.66, y: 1.35, w: 11.5, h: 0.28, fontFace: FONT, fontSize: 10.5, color: C.muted, margin: 0, fit: "shrink"});
}

function panel(slide, x, y, w, h, color = C.panel, radius = 0.08) {
  slide.addShape(pptx.ShapeType.roundRect, {x, y, w, h, rectRadius: radius, fill: {color}, line: {color: C.stroke, width: 0.8}});
}

function label(slide, text, x, y, w, color = C.cyan) {
  slide.addShape(pptx.ShapeType.roundRect, {x, y, w, h: 0.28, rectRadius: 0.05, fill: {color, transparency: 84}, line: {color, transparency: 35, width: 0.7}});
  slide.addText(text, {x, y: y + 0.01, w, h: 0.22, fontFace: FONT, fontSize: 8.5, bold: true, color, align: "center", valign: "mid", margin: 0});
}

function text(slide, value, x, y, w, h, options = {}) {
  slide.addText(value, {x, y, w, h, fontFace: FONT, fontSize: 12, color: C.text, margin: 0, breakLine: false, fit: "shrink", valign: "mid", ...options});
}

function arrow(slide, x1, y1, x2, y2, color = C.cyan, width = 1.5) {
  slide.addShape(pptx.ShapeType.line, {x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: {color, width, endArrowType: "triangle"}});
}

function stepCard(slide, n, title, desc, x, y, w, accent = C.cyan) {
  panel(slide, x, y, w, 1.04);
  slide.addShape(pptx.ShapeType.ellipse, {x: x + 0.16, y: y + 0.22, w: 0.42, h: 0.42, fill: {color: accent}, line: {color: accent}});
  text(slide, String(n), x + 0.16, y + 0.22, 0.42, 0.42, {fontSize: 12, bold: true, color: C.bg, align: "center"});
  text(slide, title, x + 0.72, y + 0.14, w - 0.86, 0.28, {fontSize: 13, bold: true, color: C.white});
  text(slide, desc, x + 0.72, y + 0.48, w - 0.86, 0.38, {fontSize: 9.3, color: C.muted, valign: "top"});
}

function metric(slide, value, caption, x, y, w, accent = C.cyan) {
  panel(slide, x, y, w, 1.18);
  text(slide, value, x + 0.12, y + 0.16, w - 0.24, 0.48, {fontSize: 25, bold: true, color: accent, align: "center"});
  text(slide, caption, x + 0.12, y + 0.73, w - 0.24, 0.22, {fontSize: 9.5, color: C.muted, align: "center"});
}

// 1 · Cover
{
  const s = pptx.addSlide();
  s.background = {color: C.bg};
  s.addShape(pptx.ShapeType.arc, {x: 8.72, y: -0.52, w: 4.85, h: 4.85, adjustPoint: 0.22, rotate: 22, fill: {color: C.cyan, transparency: 100}, line: {color: C.cyan, transparency: 68, width: 2.2}});
  s.addShape(pptx.ShapeType.arc, {x: 9.55, y: 0.22, w: 3.35, h: 3.35, adjustPoint: 0.3, rotate: 205, fill: {color: C.blue, transparency: 100}, line: {color: C.blue, transparency: 48, width: 4}});
  for (const [x, y, c] of [[10.15, 1.0, C.cyan], [11.67, 1.77, C.amber], [9.46, 2.52, C.blue], [11.04, 3.22, C.green]]) {
    s.addShape(pptx.ShapeType.ellipse, {x, y, w: 0.15, h: 0.15, fill: {color: c}, line: {color: c}});
  }
  s.addText("AGENTIC RAG · INTELLIGENT TUTORING", {x: 0.72, y: 1.02, w: 6.8, h: 0.26, fontFace: FONT, fontSize: 10, bold: true, color: C.cyan, charSpacing: 2.2, margin: 0});
  s.addText("AgenticTeacher", {x: 0.66, y: 1.54, w: 8.5, h: 0.85, fontFace: FONT, fontSize: 40, bold: true, color: C.white, margin: 0});
  s.addText("理工科 Agentic RAG 智能教学系统", {x: 0.72, y: 2.52, w: 7.3, h: 0.44, fontFace: FONT, fontSize: 20, color: C.text, margin: 0});
  s.addText("本地决策 · 服务端算力 · 教材可追溯", {x: 0.72, y: 3.15, w: 6.6, h: 0.3, fontFace: FONT, fontSize: 12, color: C.muted, margin: 0});
  const tags = [["LangGraph.js", C.cyan], ["LightRAG", C.blue], ["Qdrant", C.amber], ["Qwen3 / CUDA", C.green]];
  tags.forEach(([t, c], i) => label(s, t, 0.72 + i * 1.68, 4.18, 1.46, c));
  s.addShape(pptx.ShapeType.line, {x: 0.72, y: 6.55, w: 11.85, h: 0, line: {color: C.stroke, width: 0.8}});
  text(s, "项目技术汇报 · 2026", 0.72, 6.73, 3.2, 0.22, {fontSize: 9, color: C.muted});
}

// 2 · Product positioning
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "01 / 项目定位", "让教材知识真正进入模型回答", "面向微积分、线性代数、大学物理、化学与编程算法的可追溯智能答疑");
  const items = [
    ["资料复杂", "PDF / PPT / Markdown 中包含公式、图表与跨页语义", C.amber],
    ["一次检索不够", "口语问题、术语歧义和知识缺口需要动态反思", C.red],
    ["回答必须可信", "来源、过程、耗时可见；无证据时明确告知", C.cyan],
  ];
  items.forEach(([t, d, c], i) => {
    panel(s, 0.72, 1.95 + i * 1.34, 5.15, 1.08);
    s.addShape(pptx.ShapeType.rect, {x: 0.72, y: 1.95 + i * 1.34, w: 0.08, h: 1.08, fill: {color: c}, line: {color: c}});
    text(s, t, 1.02, 2.10 + i * 1.34, 1.25, 0.28, {fontSize: 14, bold: true, color: C.white});
    text(s, d, 2.28, 2.07 + i * 1.34, 3.25, 0.46, {fontSize: 10.5, color: C.muted});
  });
  panel(s, 6.3, 1.95, 6.28, 3.76, C.panel2);
  label(s, "核心解法", 6.64, 2.25, 1.15, C.green);
  text(s, "Agent 决定“下一步做什么”\nRAG 决定“依据什么回答”", 6.64, 2.83, 5.15, 0.92, {fontSize: 21, bold: true, color: C.white, breakLine: true, valign: "top"});
  s.addShape(pptx.ShapeType.line, {x: 6.65, y: 4.08, w: 5.28, h: 0, line: {color: C.stroke, width: 1}});
  text(s, "浏览器运行可开源 Agent；模型推理、索引、检索与资源限制由服务端执行。", 6.66, 4.38, 5.18, 0.72, {fontSize: 11.5, color: C.text, valign: "top"});
}

// 3 · Technology stack
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "02 / 技术选型", "成熟框架组合，边界清晰", "决策层保持轻量开放；算力与数据能力集中在可信服务端");
  const cols = [
    {x: 0.68, w: 3.05, color: C.cyan, tag: "CLIENT", title: "前端决策层", lines: [["Next.js 14", "App Router / UI"], ["TypeScript", "端到端类型"], ["LangGraph.js", "本地 Agent 编排"], ["KaTeX + Markdown", "公式与富文本"]]},
    {x: 3.88, w: 3.05, color: C.blue, tag: "SERVICE", title: "高算力服务层", lines: [["FastAPI + Uvicorn", "版本化 API"], ["PyTorch / CUDA", "RTX 5070 Ti"], ["Qwen3", "Embedding + Reranker"], ["Sympy", "受控符号计算"]]},
    {x: 7.08, w: 2.55, color: C.amber, tag: "RAG", title: "检索存储层", lines: [["LightRAG", "唯一 RAG 编排"], ["Qdrant", "向量后端"], ["KV + Graph", "状态与图谱"], ["Parent–Child", "语义完整性"]]},
    {x: 9.78, w: 2.85, color: C.green, tag: "MODEL", title: "云端模型层", lines: [["DeepSeek", "OpenAI-compatible"], ["Qwen", "DashScope"], ["OpenAI", "可插拔 Provider"], ["SSE", "流式生成"]]},
  ];
  cols.forEach((col) => {
    panel(s, col.x, 1.88, col.w, 4.62);
    label(s, col.tag, col.x + 0.2, 2.08, 0.92, col.color);
    text(s, col.title, col.x + 0.2, 2.56, col.w - 0.4, 0.32, {fontSize: 15, bold: true, color: C.white});
    col.lines.forEach(([name, desc], i) => {
      const yy = 3.18 + i * 0.75;
      s.addShape(pptx.ShapeType.ellipse, {x: col.x + 0.22, y: yy + 0.06, w: 0.10, h: 0.10, fill: {color: col.color}, line: {color: col.color}});
      text(s, name, col.x + 0.43, yy, col.w - 0.62, 0.24, {fontSize: 11.3, bold: true, color: C.text});
      text(s, desc, col.x + 0.43, yy + 0.28, col.w - 0.62, 0.2, {fontSize: 8.6, color: C.muted});
    });
  });
}

// 4 · System architecture
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "03 / 总体架构", "客户端决策，服务端执行", "Agent 可本地开源替换；凭证、模型、RAG 数据与配额始终留在服务端");
  const layers = [
    {y: 1.86, h: 1.16, color: C.cyan, tag: "CLIENT / BROWSER", title: "Next.js + LangGraph.js", body: "Router · Rewrite 调度 · 三轮循环 · Trace / Sources · Markdown / LaTeX"},
    {y: 3.36, h: 1.48, color: C.blue, tag: "TRUSTED SERVICE", title: "FastAPI /v1", body: "Provider Adapter  ｜  LightRAG Service  ｜  Qwen3 CUDA  ｜  Sympy  ｜  Files / Index  ｜  Usage"},
    {y: 5.20, h: 1.10, color: C.amber, tag: "DATA & MODEL", title: "持久化与外部能力", body: "Qdrant + KV / Graph Volumes        DeepSeek / Qwen / OpenAI"},
  ];
  layers.forEach((l) => {
    panel(s, 1.18, l.y, 11.0, l.h, C.panel);
    s.addShape(pptx.ShapeType.rect, {x: 1.18, y: l.y, w: 0.09, h: l.h, fill: {color: l.color}, line: {color: l.color}});
    label(s, l.tag, 1.53, l.y + 0.18, l.tag === "TRUSTED SERVICE" ? 1.48 : 1.62, l.color);
    text(s, l.title, 3.48, l.y + 0.15, 3.0, 0.32, {fontSize: 16, bold: true, color: C.white});
    text(s, l.body, 3.48, l.y + 0.55, 7.95, l.h - 0.68, {fontSize: 10.6, color: C.muted, valign: "top"});
  });
  arrow(s, 6.65, 3.03, 6.65, 3.33, C.cyan, 1.8);
  arrow(s, 6.65, 4.85, 6.65, 5.17, C.blue, 1.8);
  text(s, "HTTP / SSE", 6.87, 3.03, 1.2, 0.25, {fontSize: 8, color: C.muted});
  text(s, "检索 / 推理", 6.87, 4.88, 1.2, 0.25, {fontSize: 8, color: C.muted});
}

// 5 · Agentic loop
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "04 / Agentic RAG", "不是“一次搜索”，而是受控反思循环", "每次 Retrieve + Grade 计为一次尝试；客户端编排，服务端对最多 3 次执行硬限制");
  const xs = [0.55, 2.60, 4.65, 6.70, 8.75, 10.80];
  const nodes = [["ROUTER", "意图路由"], ["REWRITE", "学术化查询"], ["RETRIEVE", "混合召回"], ["RERANK", "Qwen3 精排"], ["GRADE", "证据充分性"], ["GENERATE", "SSE 回答"]];
  nodes.forEach(([a, b], i) => {
    panel(s, xs[i], 2.25, 1.55, 1.04, i === 4 ? "1B293D" : C.panel);
    text(s, a, xs[i] + 0.08, 2.48, 1.39, 0.22, {fontSize: 9.2, bold: true, color: i === 4 ? C.amber : C.cyan, align: "center"});
    text(s, b, xs[i] + 0.08, 2.78, 1.39, 0.23, {fontSize: 10, color: C.text, align: "center"});
    if (i < nodes.length - 1) arrow(s, xs[i] + 1.58, 2.77, xs[i + 1] - 0.08, 2.77, C.stroke, 1.3);
  });
  // Reflection loop
  s.addShape(pptx.ShapeType.line, {x: 9.52, y: 3.32, w: 0, h: 1.15, line: {color: C.amber, width: 2}});
  s.addShape(pptx.ShapeType.line, {x: 9.52, y: 4.47, w: -6.13, h: 0, line: {color: C.amber, width: 2}});
  s.addShape(pptx.ShapeType.line, {x: 3.39, y: 4.47, w: 0, h: -1.13, line: {color: C.amber, width: 2, endArrowType: "triangle"}});
  label(s, "证据不足 → 带知识缺口重写查询", 5.05, 4.26, 2.86, C.amber);
  metric(s, "≤ 3", "服务端硬限制", 0.72, 5.13, 2.32, C.amber);
  metric(s, "Top-16", "子块初始召回", 3.27, 5.13, 2.32, C.cyan);
  metric(s, "Top-4", "Reranker 最终子块", 5.82, 5.13, 2.32, C.green);
  metric(s, "1–4", "去重完整父块", 8.37, 5.13, 2.32, C.blue);
  panel(s, 10.92, 5.13, 1.72, 1.18);
  text(s, "无理想证据", 11.04, 5.34, 1.48, 0.23, {fontSize: 10, bold: true, color: C.red, align: "center"});
  text(s, "明确告知 + 世界知识", 11.04, 5.72, 1.48, 0.30, {fontSize: 8.2, color: C.muted, align: "center"});
}

// 6 · Parent-child architecture
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "05 / 父子块机制", "小块负责“找得准”，父块负责“讲得全”", "解决公式块与定义块被切断、单独公式难以召回、上下文不完整的问题");
  label(s, "INDEX", 0.72, 1.82, 0.86, C.blue);
  stepCard(s, 1, "教材小节 → 父块", "Markdown 标题 / 段落 / 页面边界\n父块上限约 8192 字符", 0.72, 2.25, 3.12, C.blue);
  stepCard(s, 2, "父块 → 子块", "默认 512 字符；保留稳定的\nchild_id → parent_id 映射", 0.72, 3.55, 3.12, C.cyan);
  stepCard(s, 3, "仅子块向量化", "Qwen3-Embedding-0.6B\n写入 LightRAG / Qdrant", 0.72, 4.85, 3.12, C.green);
  arrow(s, 2.28, 3.30, 2.28, 3.52, C.stroke);
  arrow(s, 2.28, 4.60, 2.28, 4.82, C.stroke);

  s.addShape(pptx.ShapeType.line, {x: 4.28, y: 1.84, w: 0, h: 4.48, line: {color: C.stroke, width: 1}});
  label(s, "QUERY", 4.72, 1.82, 0.92, C.amber);
  stepCard(s, 1, "查询子块向量", "LightRAG hybrid / naive\n初始召回 Top-16", 4.72, 2.25, 3.08, C.amber);
  stepCard(s, 2, "重排子块", "Qwen3-Reranker-0.6B\n固定选择前 4 个子块", 4.72, 3.55, 3.08, C.green);
  stepCard(s, 3, "回溯完整父块", "按 parent_id 映射、去重\n最终得到 1–4 个父块", 4.72, 4.85, 3.08, C.blue);
  arrow(s, 6.26, 3.30, 6.26, 3.52, C.stroke);
  arrow(s, 6.26, 4.60, 6.26, 4.82, C.stroke);

  panel(s, 8.28, 1.82, 4.35, 4.33, C.panel2);
  label(s, "RETURN TO MODEL", 8.62, 2.12, 1.60, C.cyan);
  text(s, "完整父块", 8.62, 2.65, 3.65, 0.36, {fontSize: 20, bold: true, color: C.white});
  text(s, "# 9.3 麦克斯韦方程组", 8.62, 3.18, 3.44, 0.30, {fontSize: 12, bold: true, color: C.text});
  text(s, "定义与历史背景……", 8.62, 3.67, 3.44, 0.22, {fontSize: 10, color: C.muted});
  s.addShape(pptx.ShapeType.roundRect, {x: 8.58, y: 4.10, w: 3.72, h: 0.90, rectRadius: 0.04, fill: {color: C.amber, transparency: 86}, line: {color: C.amber, transparency: 30, width: 1}});
  text(s, "∇ × E = −∂B/∂t\n∇ · E = ρ/ε₀", 8.82, 4.23, 3.26, 0.56, {fontFace: "DejaVu Sans", fontSize: 15, bold: true, color: C.amber, align: "center", breakLine: true});
  text(s, "公式 + 定义 + 推导上下文一起返回", 8.62, 5.37, 3.50, 0.32, {fontSize: 10.5, color: C.green, bold: true, align: "center"});
}

// 7 · Closed loop and observability
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "06 / 产品闭环", "从文件上传到可追溯回答", "浏览器只负责上传与展示；解析、切片、Embedding、索引和检索全部由服务端完成");
  const stages = [
    ["01", "文件摄入", "PDF / PPTX / TXT / Markdown", C.blue],
    ["02", "索引管理", "父子块统计 · 元信息 · 删除", C.cyan],
    ["03", "Agent 推理", "路由 · 三轮反思 · 计算", C.amber],
    ["04", "流式回答", "SSE · Markdown · LaTeX", C.green],
  ];
  stages.forEach(([n, t, d, c], i) => {
    const x = 0.72 + i * 3.08;
    panel(s, x, 2.05, 2.74, 1.58);
    text(s, n, x + 0.18, 2.25, 0.52, 0.30, {fontSize: 18, bold: true, color: c});
    text(s, t, x + 0.78, 2.24, 1.62, 0.28, {fontSize: 14, bold: true, color: C.white});
    text(s, d, x + 0.18, 2.82, 2.34, 0.42, {fontSize: 9.3, color: C.muted, align: "center"});
    if (i < 3) arrow(s, x + 2.77, 2.84, x + 3.00, 2.84, C.stroke, 1.3);
  });
  panel(s, 0.72, 4.10, 7.38, 1.82, C.panel2);
  label(s, "SAFE TRACE", 1.02, 4.40, 1.18, C.cyan);
  text(s, "Rewrite  →  Retrieve  →  Rerank  →  Grade  →  Generate", 1.02, 4.92, 6.70, 0.35, {fontSize: 13.5, bold: true, color: C.white});
  text(s, "展示节点、状态、耗时、来源与错误；不暴露隐藏思维链、Prompt 或密钥。", 1.02, 5.43, 6.70, 0.25, {fontSize: 9.5, color: C.muted});
  panel(s, 8.38, 4.10, 4.24, 1.82);
  label(s, "SOURCE FIRST", 8.68, 4.40, 1.26, C.green);
  text(s, "检索成功即展示父块", 8.68, 4.90, 3.54, 0.32, {fontSize: 15, bold: true, color: C.white});
  text(s, "即使生成失败，用户仍可查看命中子块高亮和教材来源。", 8.68, 5.38, 3.54, 0.38, {fontSize: 9.5, color: C.muted, valign: "top"});
}

// 8 · RTX 5070 Ti benchmark
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "07 / RTX 5070 Ti 实测", "20 秒完成教材 Index，热检索稳定在 1 秒内", "单文件 1.07 MiB；6 个物理问题 × 3 次热查询；本地 Qwen3 0.6B / CUDA BF16");
  metric(s, "20.27 s", "全链路 Index", 0.72, 1.90, 2.75, C.blue);
  metric(s, "736 / 1,986", "父块 / 子块", 3.65, 1.90, 2.75, C.cyan);
  metric(s, "0.93 s", "Query P50", 6.58, 1.90, 2.75, C.green);
  metric(s, "0.98 s", "Query P95", 9.51, 1.90, 2.75, C.amber);

  panel(s, 0.72, 3.46, 7.38, 2.25, C.panel2);
  label(s, "QUERY BREAKDOWN", 1.02, 3.76, 1.52, C.cyan);
  text(s, "903.63 ms", 1.03, 4.29, 1.62, 0.38, {fontSize: 19, bold: true, color: C.white});
  text(s, "LightRAG 检索平均", 1.03, 4.72, 1.88, 0.24, {fontSize: 9, color: C.muted});
  text(s, "848.32 ms", 3.10, 4.29, 1.72, 0.38, {fontSize: 19, bold: true, color: C.amber});
  text(s, "Qwen3 Reranker 平均", 3.10, 4.72, 2.02, 0.24, {fontSize: 9, color: C.muted});
  s.addShape(pptx.ShapeType.roundRect, {x: 5.40, y: 4.22, w: 2.22, h: 0.58, rectRadius: 0.04, fill: {color: C.amber, transparency: 82}, line: {color: C.amber, transparency: 20, width: 1}});
  text(s, "94%", 5.55, 4.29, 0.70, 0.30, {fontSize: 18, bold: true, color: C.amber, align: "center"});
  text(s, "检索耗时来自重排", 6.19, 4.29, 1.18, 0.30, {fontSize: 8.6, color: C.text, align: "center"});
  text(s, "当前首要性能瓶颈", 5.41, 5.12, 2.20, 0.24, {fontSize: 10.5, bold: true, color: C.red, align: "center"});

  panel(s, 8.38, 3.46, 4.24, 2.25);
  label(s, "BOUNDARY", 8.68, 3.76, 1.05, C.green);
  text(s, "Index：解析 + 切片 + Embedding + 写入", 8.68, 4.26, 3.50, 0.36, {fontSize: 10.5, bold: true, color: C.text});
  text(s, "Query：仅 /retrieve 端点\n不含 Rewrite 与云端回答生成", 8.68, 4.80, 3.48, 0.56, {fontSize: 10, color: C.muted, breakLine: true, valign: "top"});
  text(s, "≈ 98 子块/s", 9.10, 5.43, 2.65, 0.28, {fontSize: 12.5, bold: true, color: C.green, align: "center"});
}

// 9 · Answer ablation
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "08 / 回答消融", "父块让公式与推导重新连起来", "2 道专业题 × 4 种模式；云端生成存在随机性，关键词覆盖仅作辅助观察");
  const modes = [
    {x: 0.72, color: C.muted, tag: "NO RAG", title: "无 RAG", body: "世界知识完整\n但无教材引用、易超长", stat: "8–12 s"},
    {x: 3.72, color: C.cyan, tag: "CHILD", title: "仅子块", body: "回答简洁\n但公式与上下文易碎片化", stat: "9–17 s"},
    {x: 6.72, color: C.green, tag: "PARENT", title: "父块 RAG", body: "符号一致\n推导与教材上下文最完整", stat: "11–12 s"},
    {x: 9.72, color: C.amber, tag: "AGENTIC", title: "三轮 Agentic", body: "动态补知识面\n增加调用成本，Grade 待校准", stat: "≤ 3 轮"},
  ];
  modes.forEach((m) => {
    panel(s, m.x, 1.92, 2.68, 2.42, m.tag === "PARENT" ? C.panel2 : C.panel);
    label(s, m.tag, m.x + 0.22, 2.17, 0.96, m.color);
    text(s, m.title, m.x + 0.22, 2.66, 2.18, 0.32, {fontSize: 15, bold: true, color: C.white});
    text(s, m.body, m.x + 0.22, 3.13, 2.22, 0.56, {fontSize: 10, color: C.text, breakLine: true, valign: "top"});
    text(s, m.stat, m.x + 0.22, 3.88, 2.22, 0.24, {fontSize: 11.5, bold: true, color: m.color, align: "right"});
  });

  panel(s, 0.72, 4.72, 7.70, 1.28, C.panel2);
  label(s, "MAXWELL", 1.02, 4.98, 1.00, C.blue);
  text(s, "父块完整覆盖波动方程、v = c/√κ、E₀ = vB₀", 2.24, 4.92, 5.70, 0.32, {fontSize: 13.2, bold: true, color: C.white});
  text(s, "Agentic 三轮分别补齐“真空推导”与“介质关系”", 2.24, 5.37, 5.70, 0.24, {fontSize: 9.5, color: C.muted});

  panel(s, 8.70, 4.72, 3.92, 1.28);
  label(s, "ISSUES", 9.00, 4.98, 0.82, C.red);
  text(s, "引用约束仍不稳定", 9.98, 4.92, 2.26, 0.28, {fontSize: 12.5, bold: true, color: C.white});
  text(s, "一次 Assess 502；部分题三轮均判不足", 9.00, 5.38, 3.24, 0.24, {fontSize: 9.2, color: C.muted, align: "center"});
  text(s, "实验 Agentic 使用云端 Assess；生产 Grade 按 PROJECT.txt 使用本地分数规则", 0.74, 6.41, 11.86, 0.28, {fontSize: 9.3, color: C.amber, align: "center"});
}

// 10 · Roadmap
{
  const s = pptx.addSlide("MASTER");
  addTitle(s, "09 / 未来工作", "从“可用 MVP”走向“可评测、可扩展、可运营”", "保持本地 Agent + 服务端 LightRAG 主架构不变，持续提升数据质量与检索可信度");
  const roadmap = [
    {x: 0.72, color: C.cyan, phase: "NEXT", title: "检索质量", items: ["建立物理 / 数学 Golden Set", "报告 Recall@K、MRR 与失败类型", "校准 Grade 分数阈值"]},
    {x: 4.25, color: C.amber, phase: "MID", title: "多模态教材", items: ["公式、表格、图像版面解析", "扫描页按需 OCR / Qwen-VL", "保留坐标、provenance 与置信度"]},
    {x: 7.78, color: C.green, phase: "SCALE", title: "平台化", items: ["异步索引任务与断点恢复", "多租户 / 课程权限与密钥加密", "持久化计量、监控与成本治理"]},
  ];
  roadmap.forEach((r, idx) => {
    panel(s, r.x, 1.92, 3.15, 4.25, idx === 1 ? C.panel2 : C.panel);
    label(s, r.phase, r.x + 0.24, 2.18, 0.82, r.color);
    text(s, r.title, r.x + 0.24, 2.72, 2.62, 0.38, {fontSize: 18, bold: true, color: C.white});
    r.items.forEach((item, i) => {
      s.addShape(pptx.ShapeType.ellipse, {x: r.x + 0.27, y: 3.48 + i * 0.76, w: 0.10, h: 0.10, fill: {color: r.color}, line: {color: r.color}});
      text(s, item, r.x + 0.48, 3.36 + i * 0.76, 2.34, 0.38, {fontSize: 10.2, color: C.text, valign: "top"});
    });
  });
  arrow(s, 3.96, 4.02, 4.16, 4.02, C.stroke, 1.4);
  arrow(s, 7.49, 4.02, 7.69, 4.02, C.stroke, 1.4);
  panel(s, 11.08, 1.92, 1.55, 4.25, "0D1A29");
  text(s, "目标", 11.28, 2.25, 1.15, 0.32, {fontSize: 13, bold: true, color: C.muted, align: "center"});
  text(s, "更准\n\n更全\n\n更稳", 11.28, 3.02, 1.15, 2.36, {fontSize: 21, bold: true, color: C.cyan, align: "center", breakLine: true, valign: "mid"});
  text(s, "一条可持续演进的\nAgentic RAG 教学链路", 0.74, 6.48, 11.88, 0.34, {fontSize: 13, bold: true, color: C.white, align: "center"});
}

const output = process.argv[2] || "AgenticTeacher_项目汇报.pptx";
await pptx.writeFile({fileName: output});
console.log(output);
