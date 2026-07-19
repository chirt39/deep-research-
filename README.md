<p align="center">
  <h1 align="center">🔬 DeepResearch</h1>
  <p align="center"><strong>金融多智能体深度投研平台</strong></p>
  <p align="center">9 个 AI Agent 协作，输入股票代码，自动产出专业投研报告</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/LangGraph-1.0-ff6b35?logo=langchain" alt="LangGraph">
  <img src="https://img.shields.io/badge/DeepSeek-V3-536DFE" alt="DeepSeek">
  <img src="https://img.shields.io/badge/FastAPI-0.123-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vuedotjs" alt="Vue">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## 📖 目录

- [核心能力](#-核心能力)
- [快速开始](#-快速开始)
- [架构设计](#-架构设计)
- [工作流](#-工作流)
- [Agent 说明](#-agent-说明)
- [数据源](#-数据源)
- [配置项](#-配置项)
- [API 接口](#-api-接口)
- [项目结构](#-项目结构)
- [可选增强](#-可选增强)
- [常见问题](#-常见问题)

---

## ✨ 核心能力

> **输入一句话，输出一份报告。所有结论可溯源，全部数据源免费。**

```
用户: "深度分析比亚迪 002594"

      ↓  9 个 AI Agent 自动协作

┌──────────────────────────────────────────────────┐
│  IntentRouter     意图分流（金融关键词直判）        │
│  ChiefArchitect   五维拆解（宏观/行业/公司/估值/舆情）│
│  WebScout         网页搜索 + AKShare 金融数据       │
│  LocalRAGScout    Milvus 本地知识库检索             │
│  EvidenceJudge    证据评分 + 交叉验证 + 冲突审计     │
│  Analyst          五维投资分析 + 完备性评估          │
│  ResearchPlanner  信息缺口识别 + 补搜规划            │
│  Writer           专业研报撰写                       │
└──────────────────────────────────────────────────┘

      ↓

📄 专业投研报告（含引用溯源）

## 投资摘要        ← 核心结论 + 评级 + 目标价
## 宏观环境分析    ← 货币政策 / CPI / PMI / GDP
## 行业竞争格局    ← 市场规模 / 产业链 / 壁垒
## 公司深度分析    ← 商业模式 / 财务指标趋势
## 估值分析        ← PE/PB/PEG vs 同业 vs 历史
## 舆情与机构评级  ← 机构观点 / 资金流向
## 风险提示        ← 宏观 / 行业 / 公司三维风险
## 参考资料        ← [WEB1_1-1] 每条可追溯
```

### 亮点

- 🤖 **多 Agent 协作** — 9 个角色分工明确，从规划到撰写全自动
- 🔗 **结论可溯源** — 每条分析结论绑定 `[source_id]`，点击即可验证
- 💰 **全免费数据** — DuckDuckGo 搜索 + AKShare 金融数据，无需付费 API
- 🧠 **跨会话记忆** — PostgreSQL + Milvus 三层记忆，越用越懂你
- 📚 **本地知识库** — 灌入券商研报/年报，与公开数据交叉验证
- ⚡ **流式输出** — SSE 实时推送每个 Agent 的进度
- 🎯 **智能路由** — 简单问答秒回，复杂研究自动进入多 Agent 流程

---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Node.js 20+（前端需要）
- DeepSeek API Key → [platform.deepseek.com](https://platform.deepseek.com/api_keys)

### 1. 克隆项目

```bash
git clone https://github.com/CHIRT39-a/deep-research.git
cd deep-research
```

### 2. 安装依赖

```bash
# Python 依赖
pip install -r requirements.txt

# 前端依赖（可选，仅 Web 界面需要）
cd front/agent_front && npm install && cd ../..
```

### 3. 配置

在项目根目录创建 `.env` 或编辑 `config.json`，填入 API Key：

```bash
# .env
DEEPSEEK_API_KEY=sk-你的密钥
```

或 `config.json`：

```json
{
  "api_key": "sk-你的密钥"
}
```

> 仅此一项即可运行！其余均有默认值。

### 4. 启动

**命令行模式（最快体验）：**

```bash
python -m app.mult_agents.main --once-query "比亚迪 002594 估值分析"
```

**交互模式：**

```bash
python -m app.mult_agents.main
# 然后直接输入问题，Ctrl+C 退出
```

**Web 界面：**

```bash
# 终端 1 — 后端
python -m uvicorn app.app_main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2 — 前端
cd front/agent_front && npm run dev
```

浏览器打开 `http://localhost:5173`，输入问题即可。

---

## 🏗 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3)                    │
│                 http://localhost:5173                   │
└────────────────────────┬────────────────────────────────┘
                         │ SSE / REST
                         ▼
┌─────────────────────────────────────────────────────────┐
│                FastAPI (app_main.py)                    │
│              WorkflowService 统一入口                    │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              LangGraph StateGraph                       │
│                                                         │
│  START → intent → plan → (web_search ‖ local_rag)      │
│              ↑                    ↓                     │
│              │               deep_dive                  │
│              │                    ↓                     │
│              │                analyze                   │
│              │                 ↙    ↘                   │
│              │          [需补搜]   [证据充足]            │
│              │            ↓           ↓                 │
│              └──────── reflect      write → END         │
│                      (最多 2 轮迭代)                     │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ DeepSeek │  │DuckDuckGo│  │ AKShare  │
    │   LLM    │  │  Search  │  │  Finance │
    └──────────┘  └──────────┘  └──────────┘
```

### 技术栈

| 层 | 技术选型 | 说明 |
|---|---------|------|
| **LLM** | DeepSeek (deepseek-chat) | OpenAI 兼容协议，性价比高 |
| **编排** | LangGraph 1.0 | 有向图状态机，支持条件路由 |
| **嵌入** | HuggingFace BGE / OpenAI / DashScope | 三后端可切换，默认本地 BGE 模型 |
| **搜索** | DuckDuckGo + Bocha (可选) | 免费优先，付费增强 |
| **金融数据** | AKShare | 同花顺/东方财富，全免费 |
| **向量库** | Milvus | 知识库语义检索 |
| **记忆** | Redis + PostgreSQL + Milvus | 三层架构：短期/长期/语义 |
| **后端** | FastAPI + Uvicorn + SSE | 异步流式推送 |
| **前端** | Vue 3 + Vite + TypeScript | SPA |
| **状态持久化** | LangGraph Checkpointer | PostgreSQL / Redis / InMemory |

---

## 🔄 工作流

### 单次研究流程

| 阶段 | 节点 | 职责 | LLM |
|------|------|------|:---:|
| 0 | **IntentRouter** | 规则引擎判断 direct / multiagent，金融关键词直判 | - |
| 1 | **ChiefArchitect** | 五维拆解：生成子问题 + 大纲 + 搜索计划 | ✓ |
| 2a | **WebScout** | 网页搜索 + 金融数据采集 + 相关性过滤 | ✓ |
| 2b | **LocalRAGScout** | Milvus 知识库检索 + 证据筛选 | ✓ |
| 3 | **EvidenceJudge** | 程序化评分（可信度/去重/低置信度标记） | - |
| 4 | **Analyst** | 五维分析 + 证据完备性评估，决定是否补搜 | ✓ |
| 5 | **ResearchPlanner** | 根据信息缺口生成新的搜索词 | ✓ |
| 6 | **Writer** | 撰写最终 Markdown 研报 + 引用校验 | ✓ |

> 阶段 2a/2b 并行执行；阶段 5 仅在证据不足时触发，最多循环 2 次。

### 直接回答路径

简单问候、闲聊类问题 → IntentRouter 规则直判 → DirectResponder 秒回，不走多 Agent 流程。

---

## 🤖 Agent 说明

| Agent | 角色 | 温度 | 工具 |
|-------|------|:---:|------|
| `intent_router` | 意图路由器 | 0.0 | 规则引擎 |
| `planner` | 首席架构师 | 0.3 | - |
| `scout_web` | 网络侦察员 | 0.4 | DuckDuckGo + AKShare |
| `scout_local` | 知识库侦察员 | 0.4 | Milvus 检索 |
| `evidence_judge` | 证据裁判官 | - | 程序化评分 |
| `analyst` | 首席分析师 | 0.3 | - |
| `reflect_planner` | 补搜规划师 | 0.3 | - |
| `direct_responder` | 快速响应员 | 0.2 | - |
| `writer` | 首席撰稿人 | 0.4 | - |

---

## 📊 数据源

### 全部免费，开箱即用

| 数据源 | 用途 | 覆盖范围 | 需要 Key |
|--------|------|---------|:--------:|
| **DuckDuckGo** | 通用网页搜索 | 全球网页 | ✗ |
| **AKShare（同花顺）** | 财务指标 | ROE / 毛利率 / 净利率 / 营收增速 / 利润增速 / 负债率 | ✗ |
| **AKShare（东方财富）** | 个股信息 | PE / PB / 总市值 / 行业 / 上市日期 | ✗ |
| **AKShare（东方财富）** | 个股新闻 | 公司公告 / 舆情事件 | ✗ |
| **AKShare** | 宏观指标 | CPI / PMI / GDP / M2 / LPR / 社融 | ✗ |
| **Bocha** | 高质量搜索 | 中文网页（速度快于 DDG） | ✓ |

> 💡 **建议配置 `BOCHA_API_KEY`** 以使用 Bocha 搜索。DuckDuckGo 免费但可能被限速。去 [bocha.cn](https://ai.bocha.cn) 注册免费额度。

---

## ⚙️ 配置项

所有配置在 `config.json` 或环境变量中设置（环境变量优先级更高）。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `api_key` | - | **必填** DeepSeek API Key |
| `model` | `deepseek-chat` | LLM 模型（也支持 deepseek-reasoner） |
| `base_url` | `https://api.deepseek.com/v1` | API 地址 |
| `temperature` | `0.3` | 默认温度 |
| `max_iterations` | `2` | 最大补搜迭代次数 |
| `embedding_provider` | `huggingface` | 嵌入模型后端 |
| `embedding_model` | `BAAI/bge-small-zh-v1.5` | 嵌入模型名称 |
| `enable_memory` | `false` | 是否启用跨会话记忆 |
| `enable_milvus` | `false` | 是否启用本地知识库 |
| `checkpointer_backend` | `memory` | 状态持久化后端 |

### 环境变量对照

```bash
DEEPSEEK_API_KEY=sk-xxx          # 同 config.api_key
BOCHA_API_KEY=xxx                # Bocha 搜索 API Key（可选）
DEEPSEEK_MODEL=deepseek-chat     # LLM 模型
MAX_ITERATIONS=2                 # 最大迭代次数
EMBEDDING_PROVIDER=huggingface   # 嵌入后端
```

---

## 🔌 API 接口

### POST `/api/v1/research/run`

同步执行研究，返回最终报告。

```json
// Request
{
  "query": "比亚迪 002594 估值分析",
  "user_id": "user_001",
  "thread_id": "session_001",
  "tenant_id": "default_tenant",
  "max_iterations": 2,
  "enable_memory": true
}

// Response
{
  "final": "## 投资摘要\n比亚迪当前 PE 25x...",
  "route": "multiagent",
  "thread_id": "session_001",
  "user_id": "user_001"
}
```

### POST `/api/v1/research/stream`

SSE 流式接口，实时推送每个 Agent 的执行状态。

```bash
curl -X POST http://localhost:8000/api/v1/research/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "比亚迪估值分析", "user_id": "u1", "thread_id": "t1"}'
```

事件类型：`phase`（节点进度）、`route`（路由结果）、`final`（最终报告）、`error`（异常）。

---

## 📁 项目结构

```
deep-research/
├── app/
│   ├── app_main.py                    # FastAPI 应用入口
│   ├── backend/
│   │   ├── config/settings.py         # Web 服务配置
│   │   ├── router/
│   │   │   ├── health_router.py       # 健康检查
│   │   │   └── research_router.py     # 研究 API（run + stream）
│   │   ├── schemas/
│   │   │   ├── health.py              # 健康检查模型
│   │   │   └── research.py            # 请求/响应模型
│   │   └── service/
│   │       └── workflow_service.py    # 工作流服务（SSE + 同步）
│   └── mult_agents/                   # ★ 多智能体核心引擎
│       ├── main.py                    # CLI 入口 + Agent 工厂
│       ├── graph.py                   # LangGraph 工作流编排
│       ├── nodes.py                   # 9 个节点执行引擎
│       ├── state.py                   # 共享状态定义
│       ├── tools.py                   # 数据采集（搜索 + 金融）
│       ├── prompts.py                 # System Prompt 管理
│       ├── config.py                  # 配置加载与解析
│       ├── llm_factory.py            # LLM/嵌入模型工厂
│       ├── memory/                    # 记忆系统
│       │   ├── manager.py             # 统一记忆管理入口
│       │   ├── short_term.py          # 短期记忆（Redis/PostgreSQL）
│       │   ├── long_term.py           # 长期记忆（PostgreSQL）
│       │   └── utils.py               # 记忆提取工具
│       ├── rag/                       # 知识库系统
│       │   ├── core.py                # RAG 核心（Milvus 检索）
│       │   └── ingest.py              # 文档入库管道
│       └── test/                      # 测试脚本
├── front/agent_front/                 # Vue 3 前端
│   └── src/
│       ├── App.vue                    # 主布局
│       ├── main.ts                    # 入口
│       └── components/                # UI 组件
├── docs/                              # 详细文档（10 篇）
│   ├── 01-架构总览与配置.md
│   ├── 02-工作流与智能体.md
│   ├── 03-节点执行引擎.md
│   ├── ...
│   └── 09-部署与依赖.md
├── config.json                        # 运行时配置
├── requirements.txt                   # Python 依赖
└── README.md                          # 本文件
```

---

## 🔧 可选增强

### 本地知识库

灌入券商研报、行业白皮书、年报等内容，与公开搜索互相补充：

```bash
# 1. 启动 Milvus
docker run -d --name milvus \
  -p 19530:19530 -p 9091:9091 \
  milvusdb/milvus:latest

# 2. 灌入文档
python -m app.mult_agents.rag.ingest /path/to/your/docs

# 3. 在 config.json 中启用
# "enable_milvus": true,
# "milvus_host": "127.0.0.1",
# "milvus_port": 19530
```

### 跨会话记忆

记住用户偏好和历史研究，长期越用越智能：

```bash
# 1. 启动 PostgreSQL
docker run -d --name postgres \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  postgres:16

# 2. 在 config.json 中启用
# "enable_memory": true,
# "checkpointer_backend": "postgres",
# "postgres_dsn": "postgresql://127.0.0.1:5432/postgres"
```

### Bocha 高速搜索

DuckDuckGo 免费但可能被限速。注册 Bocha 免费额度获得更快的搜索体验：

```bash
export BOCHA_API_KEY=your_key
# 或在 config.json 中无法配置，仅支持环境变量
```

---

## ❓ 常见问题

<details>
<summary><strong>为什么一次研究要几十秒到 1-2 分钟？</strong></summary>

每次研究涉及 4-6 次 LLM 调用 + 多次网页搜索 + 金融数据 API 调用。LLM 生成、网络 I/O、数据解析都需要时间。相比人工研究的数小时，2 分钟内产出结构化研报是可以接受的。如果特别慢（>3 分钟），检查：
- DuckDuckGo 是否被限速（建议配置 `BOCHA_API_KEY`）
- 网络到 DeepSeek API 是否通畅
- 是否在没有 PostgreSQL/Redis 的环境下开启了 memory 功能
</details>

<details>
<summary><strong>支持哪些股票市场？</strong></summary>

目前主要支持 **A 股**（上海/深圳交易所）。通过 AKShare 获取同花顺+东方财富数据。港股/美股的基本搜索和分析框架同样适用，但财务数据获取需额外配置。
</details>

<details>
<summary><strong>可以分析非金融问题吗？</strong></summary>

可以。系统会通过 IntentRouter 自动判断：技术调研、方案对比、趋势分析等问题会走多 Agent 流程；简单问候会走直接回答路径。不过 Prompt 偏向金融场景，非金融分析质量可能略降。
</details>

<details>
<summary><strong>DeepSeek API 的费用如何？</strong></summary>

DeepSeek 是目前性价比最高的大模型 API 之一，deepseek-chat 约 ¥1/百万 token。一次研究报告大约消耗 10K-30K token，成本约 ¥0.01-0.03。
</details>

---
