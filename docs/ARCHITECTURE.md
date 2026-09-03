# 架构与模块说明

## 控制平面与数据平面

后端支持 Python 3.10–3.13，推荐 3.11；版本检查由 `scripts/check_python.py` 和
`pyproject.toml` 的 `requires-python` 双重保证，Python 3.14 会在安装前被拒绝。

```text
用户浏览器 / Node.js
        │  本地 LangGraph：Router → Cloud Rewrite → Retrieve/Rerank → Cloud Assess ↺ → Generate
        │  Trace、会话、取消、重试
        ▼
FastAPI /v1（可信执行与计量边界）
  ├─ provider adapter（Mock / DeepSeek / Qwen / OpenAI）
  ├─ Hugging Face Qwen3 Embedding + Qwen3 Reranker（PyTorch/CUDA 懒加载）
  ├─ LightRAG（QdrantVectorDBStorage + KV/图谱持久化）
  ├─ Sympy 受限 AST + 进程超时
  ├─ /files 临时文件与回答附件
  ├─ /index 浏览器上传后的服务端 RAG 索引
  ├─ /rag/settings、/rag/indexes 文件隔离索引管理与 Chunk 元信息
  └─ request_id、配额、usage、统一错误
        ▼
      Qdrant（LightRAG 管理的持久化向量与 payload）
```

客户端状态可被修改，服务端不信任 `iteration`、`collection`、模型或费用字段。`agent_run_id` 在整张图内固定；每个 HTTP 调用有自己的 `request_id`，同一调用重试复用 `Idempotency-Key`。

## 后端模块

- `app/main.py`：创建 FastAPI、CORS、版本化路由和统一异常响应。
- `app/config.py`：环境变量、Collection 白名单、阈值和数值上限；Compose 通过环境覆盖 Qdrant 主机名。
- `app/core/device.py`：统一解析 CPU/CUDA 与 FP32/FP16/BF16，配置 PyTorch 推理优化，并向 ready 暴露运行时和 GPU 信息。
- `app/schemas/`：Pydantic 请求/响应模型，限制消息角色、查询长度、图片和 top-k。
- `app/middleware/request_context.py`：生成/传播 `X-Request-ID`。
- `app/api/`：rewrite、retrieve、compute、generate、files、index 和 health 路由。
- `app/services/model_provider.py`：云端 provider adapter；强制 JSON Rewrite/Assess schema，Mock provider 确保无外部依赖时可运行。
- `app/services/model_settings.py`、`app/api/model_settings.py`：单用户模型配置持久化和管理接口；API Key 仅在服务端文件中保存，读取响应只返回配置状态。
- 检索接口会将本次 LightRAG 结果写入有界的短期快照缓存，`retrieval_id` 供生成接口重建上下文；快照不是持久化 RAG 数据，LightRAG 工作目录仍是索引的唯一持久来源。
- `frontend/components/markdown-renderer.tsx`：客户端动态加载的 Markdown/KaTeX 渲染器，覆盖标题、列表、引用、链接、图片、表格、代码高亮和数学公式；不信任原始 HTML，公式或渲染异常时回退为纯文本。
- `app/services/hf_models.py`：懒加载 `Qwen/Qwen3-Embedding-0.6B` 和 `Qwen/Qwen3-Reranker-0.6B`；Reranker 按官方 yes/no logits 计算相关性概率。
- `app/services/lightrag_service.py`：封装官方 LightRAG 实例、workspace/doc_id 隔离、Qwen embedding_func/rerank_model_func 和查询结果适配；生产路径不得绕过 LightRAG 手写向量 upsert。
- `app/core/telemetry.py`：脱敏单行 JSON 日志，记录请求、改写、召回、重排、证据判断、生成和首 Token 耗时。
- `app/services/compute_service.py`：AST 白名单、复杂度限制、独立进程和超时终止。
- `app/services/file_service.py`：MIME/大小校验、临时文件、哈希和过期时间。
- `app/services/usage_service.py`：演示用内存账本；生产替换为持久化计量系统。
- `ingest.py`：保留 dry-run/兼容 manifest；实际摄入入口直接交给 LightRAG。
- `app/services/index_service.py`：接收 multipart 文件，执行服务端临时落盘和解析结果交给 LightRAG pipeline，返回文档状态及统计信息；不把文件正文或向量化逻辑放到浏览器。
- `app/services/rag_registry.py`：持久化 LightRAG workspace/doc_id、文件哈希、Chunk 统计和运行时 RAG 参数。
- `app/api/rag.py`：RAG 管理设置、文件列表/详情、Chunk 查询和删除接口。
- `scripts/download_models.py`：从 Hugging Face 断点下载两个中文模型到 `MODEL_CACHE_DIR`。

## GPU 执行边界

本地 LangGraph Agent 不接触 CUDA。只有 FastAPI 内的模型加载器将张量和模型移动
到 GPU；模型首次请求时懒加载并常驻显存。`MODEL_DEVICE=auto` 允许 CPU 环境自动
降级，`MODEL_DEVICE=cuda` 则是严格部署声明：CUDA 不可用时 ready 失败。

基础 Compose 保持硬件无关；`docker-compose.gpu.yml` 通过 NVIDIA Container
Runtime 预留一张 GPU，并将宿主机模型缓存绑定到 `/app/models`。容器镜像无需携带
NVIDIA 内核驱动，驱动设备与库由运行时注入；Python 依赖中的 CUDA 版 PyTorch
提供用户态 CUDA 运行库。

## 前端模块

- `frontend/lib/agent.ts`：本地路由与最多三次检索反思循环；计算题走 compute，混合题走 Hybrid Tool。
- `frontend/lib/api.ts`：统一 fetch、超时、Zod 运行时校验和 POST SSE 解析；按 `(request_id, stream, seq)` 去重。
- `frontend/hooks/useAgenticChat.ts`：Zustand 会话状态、取消/错误状态和增量 token 合并。
- `frontend/components/chat-shell.tsx`：学科选择、聊天气泡、Trace/Sources 面板、LaTeX 快捷按钮、图片拖拽上传和 RAG 管理入口。
- `frontend/components/rag-management.tsx`、`frontend/app/rag/page.tsx`：独立 RAG 管理页，负责参数配置、文件索引、Chunk 元信息查看和删除。

## SSE 生命周期

1. Generate 返回 `trace(running)`。
2. 返回 `source` 事件，前端更新来源卡片。
3. 以 chunk 返回 `token`，前端节流渲染 Markdown/LaTeX。
4. 成功返回 `done + usage`；失败返回 `error`。客户端断开时服务端仍在 finally/后台记录实际 provider usage。

## 生产替换点

当前链路为“LightRAG workspace/doc_id 隔离 → Qwen Embedding → LightRAG hybrid/naive 检索 → Qwen Reranker Top-4 → 云端证据评估 → 最多三轮反思 → Provider 生成”。服务端按 `agent_run_id` 强制三轮上限；三轮不足时记录 warning、插入用户可见声明并允许模型使用通用知识。首次使用前运行 `python scripts/download_models.py --cache-dir ./models`，并在 GPU 部署设置 `HF_LOCAL_FILES_ONLY=true`、`HF_ENABLE_RERANKER=true`。
