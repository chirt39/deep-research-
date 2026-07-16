"""工具模块：封装 Web 检索、本地 RAG 查询与通用辅助工具函数。"""

from datetime import datetime
import ast
import json
import logging
import operator
import os
from pathlib import Path
import urllib.error
import urllib.request

from langchain_core.tools import tool
from typing import Optional
from .rag.core import RAGSystem, RAGConfig

logger = logging.getLogger("mult_agents")

# 全局 RAG 系统实例
_RAG_SYSTEM: Optional[RAGSystem] = None

def init_rag_system(api_key: str, config: Optional[RAGConfig] = None):
    """初始化全局 RAG 系统"""
    global _RAG_SYSTEM
    if _RAG_SYSTEM is None:
        try:
            _RAG_SYSTEM = RAGSystem(api_key, config)
        except Exception as e:
            print(f"RAG 系统初始化失败: {e}")


def search_knowledge_base_records(query: str, limit: int = 5) -> list[dict]:
    if _RAG_SYSTEM is None:
        return []
    try:
        return _RAG_SYSTEM.search_records(query, k=limit)
    except Exception:
        return []


def bocha_web_search_records(query: str, count: int = 8) -> list[dict]:
    api_key = os.getenv("BOCHA_API_KEY", "").strip()
    logger.info("[bocha_web_search] 开始搜索 | query=%s | count=%s", query, count)
    logger.info("[bocha_web_search] API Key 状态 | 是否配置=%s | Key前缀=%s", bool(api_key), api_key[:8] + "..." if api_key else "None")
    if not api_key:
        logger.warning("[bocha_web_search] 未配置 BOCHA_API_KEY，跳过搜索")
        return []
    payload = {
        "query": query,
        "summary": True,
        "freshness": "noLimit",
        "count": count,
    }
    request = urllib.request.Request(
        url="https://api.bocha.cn/v1/web-search",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        logger.info("[bocha_web_search] 发送请求 | url=%s", request.full_url)
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            logger.info("[bocha_web_search] 收到响应 | status=%s | content_length=%s", response.status, len(raw))
        result = json.loads(raw)
        logger.info("[bocha_web_search] 解析响应成功 | data字段存在=%s", "data" in result)
    except urllib.error.HTTPError as e:
        logger.error("[bocha_web_search] HTTP 错误 | code=%s | reason=%s", e.code, e.reason)
        return []
    except urllib.error.URLError as e:
        logger.error("[bocha_web_search] URL 错误 | reason=%s", e.reason)
        return []
    except json.JSONDecodeError as e:
        logger.error("[bocha_web_search] JSON 解析错误 | error=%s", e)
        return []
    except Exception as e:
        logger.error("[bocha_web_search] 未知错误 | error=%s | type=%s", e, type(e).__name__)
        return []
    data = result.get("data", {})
    pages = data.get("webPages", [])
    logger.info("[bocha_web_search] 解析数据 | webPages类型=%s", type(pages).__name__)
    if isinstance(pages, dict):
        if isinstance(pages.get("value"), list):
            pages = pages.get("value", [])
        elif isinstance(pages.get("items"), list):
            pages = pages.get("items", [])
        else:
            pages = []
    if not isinstance(pages, list):
        logger.warning("[bocha_web_search] webPages 格式异常 | type=%s", type(pages).__name__)
        return []
    logger.info("[bocha_web_search] 获取网页数量 | total=%s", len(pages))
    records: list[dict] = []
    for idx, page in enumerate(pages[:count], 1):
        if not isinstance(page, dict):
            logger.warning("[bocha_web_search] 第 %s 条记录格式异常 | type=%s", idx, type(page).__name__)
            continue
        url = str(page.get("url") or "").strip()
        domain = ""
        if "://" in url:
            domain = url.split("://", 1)[1].split("/", 1)[0]
        title = page.get("name") or f"web_result_{idx}"
        snippet = page.get("summary") or ""
        logger.info("[bocha_web_search] 解析记录 %s | title=%s | url=%s | snippet长度=%s", idx, title[:50], domain, len(snippet))
        records.append(
            {
                "source_id": f"WEB-{idx}",
                "title": title,
                "url": url,
                "snippet": snippet,
                "domain": domain,
                "source_type": "web",
                "published_at": page.get("datePublished") or page.get("dateLastCrawled") or "",
            }
        )
    logger.info("[bocha_web_search] 搜索完成 | 返回记录数=%s", len(records))
    return records

@tool
def search_knowledge_base(query: str) -> str:
    """
    查询本地知识库/向量数据库。
    当用户询问关于专业知识、历史文档或私有数据时使用此工具。
    输入应该是具体的查询问题。
    """
    if _RAG_SYSTEM is None:
        return "错误：RAG 系统未初始化或连接失败。请检查 Milvus 服务状态。"
    return _RAG_SYSTEM.search(query)


ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}


def _eval_node(node):
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_OPERATORS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return ALLOWED_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    raise ValueError("Unsupported expression")


@tool
def get_current_time() -> str:
    """返回当前时间的 ISO 字符串。"""
    return datetime.now().isoformat()


@tool
def simple_calculator(expression: str) -> str:
    """计算简单算术表达式并返回结果。"""
    tree = ast.parse(expression, mode="eval")
    result = _eval_node(tree.body)
    return str(result)


@tool
def extract_requirements(text: str) -> str:
    """从文本中提取需求要点列表。"""
    items = [part.strip() for part in text.replace("\n", " ").split("。") if part.strip()]
    return "\n".join(f"- {item}" for item in items[:8])


@tool
def outline_from_topics(topics: str) -> str:
    """根据主题列表生成编号大纲。"""
    raw = topics.replace("\n", ",")
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return "\n".join(f"{idx+1}. {item}" for idx, item in enumerate(items[:10]))


@tool
def merge_notes(note_a: str, note_b: str) -> str:
    """合并两段文本为一段笔记。"""
    return f"{note_a}\n{note_b}".strip()


@tool
def summarize_points(text: str) -> str:
    """从文本中抽取要点列表。"""
    sentences = [s.strip() for s in text.replace("\n", " ").split("。") if s.strip()]
    points = sentences[:6]
    return "\n".join(f"- {p}" for p in points)


@tool
def dedupe_lines(text: str) -> str:
    """对文本按行去重并输出。"""
    seen = set()
    lines = []
    for line in text.splitlines():
        key = line.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines)


@tool
def web_search_stub(query: str) -> str:
    """网络检索接口（Bocha Web Search）。"""
    records = bocha_web_search_records(query, count=5)
    if not records:
        return "未配置 BOCHA_API_KEY，无法执行网络检索。"
    lines = ["Bocha 检索结果："]
    for idx, record in enumerate(records, 1):
        lines.append(f"{idx}. {record['title']}")
        url = record.get("url", "")
        if url:
            lines.append(f"   链接: {url}")
        snippet = record.get("snippet", "")
        if snippet:
            lines.append(f"   摘要: {snippet[:200]}")
    return "\n".join(lines)


@tool
def local_docs_lookup_stub(query: str) -> str:
    """模拟本地检索接口。"""
    return f"未配置本地检索服务，收到查询: {query}"


@tool
def local_vector_search_stub(query: str) -> str:
    """模拟向量数据库检索接口。"""
    return f"未配置向量数据库，收到查询: {query}"


@tool
def optimize_query(query: str) -> str:
    """对检索问题进行改写与优化。"""
    return f"优化后的查询建议: {query}"


@tool
def explain_term(term: str) -> str:
    """解释领域术语。"""
    return f"{term} 需要结合上下文进一步解释"


@tool
def python_inter(code: str) -> str:
    """模拟 Python 执行环境。"""
    return f"未配置Python执行环境，收到代码: {code}"


@tool
def fig_inter(spec: str) -> str:
    """模拟绘图执行环境。"""
    return f"未配置绘图环境，收到图表需求: {spec}"


@tool
def amap_weather(city: str) -> str:
    """模拟高德天气查询。"""
    return f"未配置高德API，收到天气查询: {city}"


@tool
def amap_geocode(address: str) -> str:
    """模拟高德地理编码。"""
    return f"未配置高德API，收到地理编码请求: {address}"


@tool
def amap_poi_search(query: str) -> str:
    """模拟高德 POI 检索。"""
    return f"未配置高德API，收到POI检索: {query}"


@tool
def amap_route_plan(origin: str, destination: str) -> str:
    """模拟高德路径规划。"""
    return f"未配置高德API，收到路径规划: {origin} -> {destination}"


def _workspace_root() -> Path:
    base = os.getenv("WORKSPACE_DIR", "/workspace")
    return Path(base).resolve()


def _safe_path(path: str) -> Path:
    root = _workspace_root()
    target = (root / path).resolve()
    if root not in target.parents and target != root:
        raise ValueError("路径超出工作目录")
    return target


@tool
def safe_list_dir(path: str = ".") -> str:
    """安全列出工作目录下的文件与子目录。"""
    root = _workspace_root()
    if not root.exists():
        return f"工作目录不存在: {root}"
    target = _safe_path(path)
    if not target.exists() or not target.is_dir():
        return "目录不存在"
    items = [p.name for p in target.iterdir()]
    return "\n".join(items)


@tool
def safe_read_file(path: str) -> str:
    """安全读取工作目录内的文件。"""
    root = _workspace_root()
    if not root.exists():
        return f"工作目录不存在: {root}"
    target = _safe_path(path)
    if not target.exists() or not target.is_file():
        return "文件不存在"
    return target.read_text(encoding="utf-8")


@tool
def safe_write_file(path: str, content: str) -> str:
    """安全写入工作目录内的文件。"""
    root = _workspace_root()
    if not root.exists():
        return f"工作目录不存在: {root}"
    target = _safe_path(path)
    if not target.parent.exists():
        return "目录不存在"
    target.write_text(content, encoding="utf-8")
    return f"已写入: {target}"


@tool
def safe_move_file(src: str, dst: str) -> str:
    """安全移动工作目录内的文件。"""
    root = _workspace_root()
    if not root.exists():
        return f"工作目录不存在: {root}"
    src_path = _safe_path(src)
    dst_path = _safe_path(dst)
    if not src_path.exists():
        return "源文件不存在"
    if not dst_path.parent.exists():
        return "目标目录不存在"
    src_path.replace(dst_path)
    return f"已移动: {dst_path}"


@tool
def sql_inter(query: str) -> str:
    """模拟 SQL 执行接口。"""
    return f"未配置数据库，收到SQL: {query}"


@tool
def extract_data_stub(query: str) -> str:
    """模拟数据抽取接口。"""
    return f"未配置数据抽取环境，收到请求: {query}"


@tool
def execute_terminal_command(command: str) -> str:
    """模拟终端命令执行接口。"""
    return f"未配置终端执行环境，收到命令: {command}"


@tool
def file_operation_stub(request: str) -> str:
    """模拟文件操作接口。"""
    return f"未配置文件操作环境，收到请求: {request}"


@tool
def news_search_stub(query: str) -> str:
    """模拟新闻检索接口。"""
    return f"未配置新闻检索服务，收到查询: {query}"


@tool
def finance_search_stub(query: str) -> str:
    """模拟金融检索接口。"""
    return f"未配置金融检索服务，收到查询: {query}"


@tool
def extract_url_content_stub(url: str) -> str:
    """模拟 URL 内容抽取接口。"""
    return f"未配置URL解析服务，收到URL: {url}"
