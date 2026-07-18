# DeepResearch — 金融多智能体深度投研平台

> 输入股票代码，9 个 AI Agent 自动完成宏观研判 → 行业分析 → 公司深度 → 估值模型 → 舆情跟踪，输出专业投研报告。所有结论可溯源，数据源全部免费。

---

## 核心能力

```
用户: "深度研究比亚迪002594"
  │
  ▼
┌─────────────────────────────────────────────────────┐
│  IntentRouter    →  意图分流（金融关键词直判）        │
│  ChiefArchitect  →  五维拆解（宏观/行业/公司/估值/舆情）│
│  WebScout        →  DuckDuckGo 网页搜索 + AKShare 金融数据│
│  LocalRAGScout   →  Milvus 知识库检索               │
│  EvidenceJudge   →  证据评分 + 交叉验证 + 冲突审计    │
│  Analyst         →  五维投资分析 + 完备性评估        │
│  ResearchPlanner →  信息缺口补搜                     │
│  Writer          →  3000+ 字专业研报                  │
└─────────────────────────────────────────────────────┘
  │
  ▼
## 投资摘要
比亚迪当前 PE 25x，低于行业均值 32x...
## 宏观环境分析
## 行业竞争格局
## 公司深度分析  ← 含财务指标趋势
## 估值分析      ← PE/PB/PS vs 同业 vs 历史分位
## 舆情与机构评级
## 风险提示
## 参考资料      ← 每条结论绑 source_id，可追溯
```

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/CHIRT39-a/deep-research.git
cd deep-research

pip install -r requirements.txt
cd front/agent_front && npm install && cd ../..
```

### 2. 配置

只需一行——在 `config.json` 或 `.env` 中填入 DeepSeek API Key：

```json
{ "api_key": "sk-你的DeepSeek密钥" }
```

> 去 [platform.deepseek.com](https://platform.deepseek.com/api_keys) 注册获取

### 3. 启动

```bash
# 终端 1 — 后端
python -m uvicorn app.app_main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2 — 前端
cd front/agent_front && npm run dev
```

浏览器打开 `http://localhost:5173`

### 命令行模式（不需要前端）

```bash
python -m app.mult_agents.main --once-query "比亚迪002594估值分析"
```

---

## 数据源（全部免费）

| 数据源 | 用途 | 需要配置 |
|--------|------|----------|
| DuckDuckGo | 网页搜索 | 无，开箱即用 |
| AKShare（同花顺） | 财务指标（ROE/毛利率/增速/负债率） | 无 |
| AKShare（东方财富） | 个股新闻 | 无 |
| Bocha（可选） | 高质量网页搜索 | BOCHA_API_KEY |

---

## 可选增强

```bash
# 本地知识库 — 灌入券商研报/白皮书/年报
docker run -d --name milvus -p 19530:19530 milvusdb/milvus:latest
python -m mult_agents.rag.ingest /path/to/docs

# 跨会话记忆
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
# 在 .env 中配置 POSTGRES_DSN + ENABLE_MEMORY=true
```

---

## 项目结构

```
deep_research/
├── app/
│   ├── app_main.py              ← FastAPI 入口
│   ├── backend/                 ← Web 服务层
│   └── mult_agents/             ← 多智能体核心引擎
│       ├── graph.py             ← LangGraph 工作流编排
│       ├── nodes.py             ← 节点执行引擎
│       ├── prompts.py           ← 9 个 Agent 的 System Prompt
│       ├── state.py             ← 共享状态定义
│       ├── tools.py             ← 数据采集（DuckDuckGo + AKShare）
│       ├── llm_factory.py       ← LLM 工厂（DeepSeek + 多后端嵌入）
│       ├── config.py            ← 配置加载
│       ├── memory/              ← 记忆系统（短期 + 长期 + 语义）
│       └── rag/                 ← 知识库系统（Milvus 向量检索）
├── front/agent_front/           ← Vue.js 前端
├── docs/                        ← 详细解析文档（10 篇）
├── config.json                  ← 运行时配置
├── requirements.txt             ← Python 依赖
└── README.md
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| LLM | DeepSeek（deepseek-chat / deepseek-reasoner） |
| 编排 | LangGraph 状态图 |
| 嵌入 | HuggingFace BGE / OpenAI / DashScope |
| 数据 | AKShare + DuckDuckGo + Bocha |
| 向量库 | Milvus |
| 记忆 | Redis + PostgreSQL + Milvus |
| 后端 | FastAPI + Uvicorn + SSE 流式 |
| 前端 | Vue 3 + Vite + TypeScript |

---

## 文档

完整代码解析见 [docs/](docs/) 目录：

| 文档 | 内容 |
|------|------|
| [架构总览](docs/01-架构总览与配置.md) | 系统全景、数据流、配置体系 |
| [工作流与智能体](docs/02-工作流与智能体.md) | State、Graph、9 个 Prompt、执行时序 |
| [节点执行引擎](docs/03-节点执行引擎.md) | nodes.py 逐函数解析 |
| [数据工具层](docs/04-数据工具层.md) | DuckDuckGo + AKShare 全部函数 |
| [记忆系统](docs/05-记忆系统.md) | 三层记忆架构 + Prompt 注入 |
| [知识库系统](docs/06-知识库系统.md) | Milvus RAG + 文档入库 |
| [后端服务层](docs/07-后端服务层.md) | FastAPI + SSE + WorkflowService |
| [前端界面](docs/08-前端界面.md) | Vue.js + Markdown 渲染器 |
| [部署与依赖](docs/09-部署与依赖.md) | 启动方式 + 环境变量 + FAQ |

---

## License

MIT
