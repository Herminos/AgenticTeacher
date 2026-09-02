# Agentic Teacher

理工科全科目 Agentic RAG 智能教学系统的可运行骨架。项目保留 `PROJECT.txt` 定义的核心架构：浏览器/Node.js 本地运行 LangGraph Agent，FastAPI 提供模型、检索、文件和受控计算能力。

## 目录

```text
app/                         FastAPI 服务
  api/                       /v1 API、文件和 health 路由
  core/                      预留模型加载扩展点
  middleware/                request_id 中间件
  schemas/                   Pydantic 契约
  services/                  provider、Qdrant、Sympy、文件和 usage 服务
  tests/                     后端契约测试
ingest.py                    离线解析、分块、HyDE 和幂等摄入
config/                      Collection/Grade 配置
frontend/                    Next.js 14 + LangGraph.js 前端
PROJECT.txt                  完整技术规格（实现边界的唯一来源）
```

## 快速启动

项目要求 Python `>=3.10,<3.14`，推荐 Python 3.11。不要直接使用 Python 3.14：当前固定的 `pydantic-core` 依赖会退回 Rust/PyO3 本地编译，而该版本的 PyO3 不支持 3.14。

Linux/macOS 可以直接使用项目提供的 bootstrap 脚本：

```bash
./scripts/bootstrap.sh
source .venv/bin/activate
```

脚本会先执行版本检查，再创建虚拟环境和安装依赖。如果系统中的默认 `python3` 是 3.14，请显式指定已安装的兼容版本：

```bash
PYTHON_BIN=python3.11 ./scripts/bootstrap.sh
```

也可以手动执行：

```bash
cp .env.example .env
python3.11 scripts/check_python.py
python3.11 -m venv .venv && source .venv/bin/activate
python scripts/check_python.py
pip install -r requirements.txt

# 可选：预下载中文本地 RAG 模型（首次实际摄入/检索也会自动下载）
python scripts/download_models.py --cache-dir ./models

# 仅启动 Qdrant + API；API 默认使用 mock provider，无需 GPU 或 API Key
docker compose up -d qdrant api
curl http://localhost:8000/health/ready

# 没有教材时可跳过；有教材时执行
python ingest.py --dir ./data/微积分 --collection lecture_math --dry-run

# 安装并启动前端
npm install --prefix frontend
npm run dev
```

浏览器访问 <http://localhost:3000>。Compose 内 API 使用 `http://qdrant:6333`，宿主机运行 `ingest.py` 时使用 `http://localhost:6333`。

## RTX 50 系列 GPU 推理

本项目的本地模型引擎是 PyTorch + Hugging Face Transformers。浏览器仍只运行
LangGraph 决策流程；Qwen 嵌入和查询改写模型只在 FastAPI 进程中使用 GPU。
`MODEL_DEVICE=auto` 会在 CUDA 可用时自动选择 GPU，RTX 5070 Ti 默认使用 BF16；
显式 CPU 模式使用 FP32。

宿主机运行前先确认当前虚拟环境中的 PyTorch 能识别显卡：

```bash
nvidia-smi
.venv/bin/python -c "import torch; print(torch.__version__, torch.version.cuda); print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"

MODEL_DEVICE=cuda MODEL_DTYPE=bfloat16 \
HF_ENABLE_LOCAL_MODELS=true HF_LOCAL_FILES_ONLY=true \
MODEL_CACHE_DIR=./models \
  .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Docker GPU 部署还要求安装 NVIDIA Container Toolkit。先验证容器运行时，再叠加
GPU override 启动；基础 `docker-compose.yml` 不强制要求显卡，因此 CPU/Mock
环境仍能正常使用。

```bash
docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi

docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  up -d --build qdrant api

curl http://localhost:8000/health/ready
```

GPU override 会把宿主机的 `./models` 只作为模型缓存挂载到 `/app/models`，并设置
`MODEL_DEVICE=cuda`、`MODEL_DTYPE=bfloat16`。ready 响应中应看到
`runtime.cuda_available: true`、`model_device: "cuda"` 和显卡名称。若显式 CUDA
部署未把 GPU 暴露给容器，ready 会返回 `ready: false` 和清晰的配置错误，不会
静默回退 CPU。停止服务时使用同一组 compose 文件：

API 镜像保留了最小 GCC 运行工具链。PyTorch/Triton 会在特定模型算子第一次执行
时即时编译 GPU kernel；只验证 `torch.cuda.is_available()` 不足以发现这一要求，
因此不要从 Dockerfile 中删除 `gcc` 和 `libc6-dev`。

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml down
```

Compose 使用精简版 Qdrant 镜像，不依赖镜像内的 `wget`/`curl` 做容器健康检查；Qdrant 主进程检查通过后，API 会在 `/health/ready` 中通过 HTTP 再次验证 Qdrant 和模型 provider。若之前的旧配置报 `qdrant is unhealthy`，执行以下命令重建容器即可：

```bash
docker compose down
docker compose up -d qdrant api
curl http://localhost:8000/health/ready
```

如果看到 `pyo3-ffi ... Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)`，说明使用了错误的解释器。不要反复重试 pip；退出当前虚拟环境，使用 `python3.11 -m venv .venv` 或 `PYTHON_BIN=python3.11 ./scripts/bootstrap.sh` 重建环境。Docker 部署不受此问题影响，因为 [`Dockerfile`](Dockerfile) 固定使用 Python 3.10。

如果前端构建时报 `UnhandledSchemeError: Reading from "node:async_hooks"`，通常是直接从 `@langchain/langgraph` 默认入口打包导致的 Node-only 模块进入浏览器。项目已统一使用 `@langchain/langgraph/web`，并让聊天界面通过客户端动态加载；请确认没有把默认入口重新改回去。清理缓存后重新构建即可：

```bash
rm -rf frontend/.next
NEXT_TELEMETRY_DISABLED=1 npm run build --prefix frontend
```

若仍出现 `/page` 预渲染错误，请检查新增组件是否在模块顶层访问 `window`、`document` 或 Node 内置模块；浏览器专用逻辑应放在客户端组件或 `next/dynamic(..., { ssr: false })` 加载的模块中。

### Docker 报 `failed to add the host veth... operation not supported`

这不是 API 或 Qdrant 配置错误，而是当前 Linux 内核没有提供 Docker bridge 所需的 `veth` 模块。先确认：

```bash
test -e /sys/module/veth && echo veth-ok || echo veth-missing
modprobe veth
```

如果你刚更新过内核，先检查是否只是尚未重启：

```bash
uname -r
pacman -Q linux-zen
```

运行中的 `uname -r` 必须与已安装内核的版本一致。内核更新后旧内核仍在运行时，`modprobe veth` 会在旧版本的模块目录中找不到文件；重启并在启动菜单选择最新 `linux-zen` 后即可恢复。当前 Arch `linux-zen` 包仍包含 `drivers/net/veth.ko`，这不是近期被移除的功能。

推荐修复是启动一个带 veth 支持的发行版内核（Arch Linux 通常安装并重启到 `linux`/`linux-lts` 内核），然后重启 Docker：

```bash
sudo pacman -S linux linux-headers   # 或 linux-lts linux-lts-headers
sudo reboot
sudo modprobe veth
sudo systemctl restart docker
docker compose up -d qdrant api
```

如果暂时不能更换内核，可使用项目提供的 host-network 备用 Compose。该模式不创建 bridge/veth，API 和 Qdrant 共用主机网络，通常只适用于单机开发：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.host.yml up -d qdrant api
curl http://localhost:8000/health/ready
```

host-network 模式会牺牲容器网络隔离；恢复正常内核后应回到默认的 `docker-compose.yml`（必要时先执行 `docker compose down`）。

## API

- `POST /v1/rewrite`：口语查询改写。
- `POST /v1/assess`：由当前云端模型以严格 JSON 判断 Top-5 教材证据是否足够，并给出下一轮检索短语。
- `POST /v1/retrieve`：固定召回 Top-15，使用 Qwen3-Reranker-0.6B 重排后只返回 Top-5；开发环境没有 Qdrant 数据时使用确定性的内存 demo 语料。
- `POST /v1/compute`：受限 AST + 独立进程执行 Sympy，禁止 `eval/exec`。
- `POST /v1/generate`：POST SSE，前端使用 `fetch + ReadableStream`；事件包括 `trace/source/token/error/done`。
- `POST /v1/files`：上传回答图片或排队的 PDF/PPT 索引源；`answer_attachment` 默认 10 MB，`ingest_source` 单文件默认 10 GB。
- `POST /v1/index`：接收浏览器选择的一个或多个 PDF/PPTX/TXT/Markdown 文件，服务端完成解析、分块、嵌入和 Qdrant upsert，并返回索引耗时、文件数、chunk 数和新增数量。
- `GET /v1/providers`：返回可用模型供应商及默认 Base URL/模型（不返回密钥）。
- `GET /health/live`、`GET /health/ready`：进程和依赖就绪检查。

前端顶部“模型设置”目前仅支持 Mock、DeepSeek、通义千问 Qwen 和 OpenAI / ChatGPT。模型名称使用按供应商联动的下拉菜单选择，Base URL、Temperature 和个人 API Key 仍可配置。默认模型依据官方文档配置为：DeepSeek `deepseek-v4-pro`（`https://api.deepseek.com`）、Qwen `qwen3.8-max`（DashScope OpenAI-compatible endpoint）和 OpenAI `gpt-5.6-sol`（`https://api.openai.com/v1`）。设置仅保存在当前页面内存中，并随本次请求传给 FastAPI；后端不会把密钥写入日志、Trace、会话或响应。生产环境应使用 HTTPS、短期鉴权，或改为在服务端 `.env` 配置统一密钥。默认 Mock provider 无需任何外部模型即可完成 Rewrite → Retrieve（内存演示语料）→ Grade → Generate 闭环。

前端顶部的“RAG Index”面板支持“选择文件”和“选择目录”（浏览器通过 `webkitdirectory` 提交目录内文件）。文件内容不会在浏览器端解析或向量化；前端仅以 multipart 上传，服务端按当前学科映射到白名单 Collection。索引完成后会显示 `index_id`、Collection、Embedding 模型、处理耗时、文件数、总 chunks 和新增 chunks。单次最多 100 个文件，默认单文件和单次总大小均为 10 GB，可通过 `MAX_INDEX_FILES`、`MAX_INDEX_FILE_MB`、`MAX_INDEX_TOTAL_MB` 和 `INDEX_TIMEOUT_MS` 调整。索引服务会分块流式写入临时磁盘，不会把整个大文件一次性读入内存；请确保 `/tmp` 所在磁盘有足够空间。

## 本地 Agent

`frontend/lib/agent.ts` 定义路由、云端 JSON Rewrite → Top-15 Retrieve → Qwen Top-5 Rerank → 云端 Evidence Assess（最多 3 次）、Hybrid Compute Tool 和 Generate 流程，同时导出编译后的 LangGraph 图。寒暄、身份询问等由 Rewrite 返回空 JSON，Agent 会跳过 RAG。客户端的 `max_iterations` 只是默认值，服务端按 `agent_run_id` 再次强制三轮上限。

三轮检索仍被云端模型判定为证据不足时，后端会记录 `rag_exhausted_world_knowledge_fallback` warning，并在回答正文前强制加入“未在已索引教材中找到足够相关片段，以下基于模型通用知识回答”，不会伪造教材来源。

## 摄入

`ingest.py` 优先读取 PDF/PPT 原生文本，对复杂页可安装 `pymupdf`/`python-pptx` 并接入视觉/OCR provider。Chunk 按段落语义切分，保留 `source_id/chunk_id/page/content_hash`；`--hyde-count` 控制 0–3 个假设问题。连接 Qdrant 时，服务端会懒加载 Hugging Face `Qwen/Qwen3-Embedding-0.6B`，按模型实际 hidden size 创建/校验 `text_dense` Collection，并使用同一模型编码查询和文档；Qdrant 不可用时才回退到内存演示语料。查询改写和证据评估统一使用当前配置的 DeepSeek/Qwen/OpenAI 云端模型，本地不再下载或加载 Qwen2 改写模型。

首次使用本地模型前安装 requirements，并可预下载权重（约数百 MB 至数 GB，取决于 Hugging Face 缓存和 Transformers 版本）：

```bash
python scripts/download_models.py --cache-dir ./models
HF_ENABLE_LOCAL_MODELS=true HF_ENABLE_RERANKER=true HF_LOCAL_FILES_ONLY=true \
  uvicorn app.main:app --reload --port 8000
```

模型下载和推理始终只发生在 FastAPI 服务端；浏览器不会加载 Transformers 或 Torch。
Qwen3-Embedding-0.6B 与 Qwen3-Reranker-0.6B 在 16 GB 显存的 RTX 5070 Ti 上可使用 BF16 懒加载。CPU 机器首次加载可能需要几十秒；基础 Compose 默认关闭 Reranker，GPU override 默认启用。

## 结构化日志与耗时

后端向标准输出写入单行 JSON 日志，不记录 API Key、完整 Prompt、文档正文或隐藏推理。每条日志通过 `request_id`、`agent_run_id` 关联，覆盖 HTTP 总耗时、云端改写、每轮 RAG、Qwen Reranker、证据评估、符号计算、首 Token 和完整生成耗时：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs -f api
```

典型事件包括 `model_rewrite`、`rag_retrieval`、`evidence_assessment`、`symbolic_compute`、`model_generation` 和 `http_request`。前端 Trace 同时展示各节点的 `duration_ms`。

可用的精度设置为 `auto/float32/float16/bfloat16`。`auto` 在支持 BF16 的 CUDA
显卡上选择 BF16，在其他 CUDA 显卡上选择 FP16，在 CPU 上选择 FP32。不要在
CPU 模式设置 FP16；服务会拒绝这一无效组合。

## 测试

```bash
pytest
npm test --prefix frontend
```

后端测试覆盖 health、rewrite、retrieve、SSE 和 Sympy 安全边界；前端测试确认 LangGraph 模块可加载。上线前应补充真实模型 provider、检索 golden set（Recall@K/MRR）、视觉解析回归和 Playwright 端到端测试。

详细模块职责和事件/状态流见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 许可证

项目源代码采用 [MIT License](LICENSE) 开源。第三方依赖、模型权重以及用户上传的教材或其他内容仍分别受其各自许可证和权利约束。
