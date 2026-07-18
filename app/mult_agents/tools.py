"""工具模块：封装 Web 检索、本地 RAG 查询与金融数据采集。"""

import json
import logging
import os
import urllib.error
import urllib.request

from typing import Optional
from .rag.core import RAGSystem, RAGConfig

logger = logging.getLogger("mult_agents")

# 全局 RAG 系统实例
_RAG_SYSTEM: Optional[RAGSystem] = None

def init_rag_system(config: Optional[RAGConfig] = None):
    """初始化全局 RAG 系统"""
    global _RAG_SYSTEM
    if _RAG_SYSTEM is None:
        try:
            _RAG_SYSTEM = RAGSystem(config)
        except Exception as e:
            print(f"RAG 系统初始化失败: {e}")


def search_knowledge_base_records(query: str, limit: int = 5) -> list[dict]:
    if _RAG_SYSTEM is None:
        return []
    try:
        return _RAG_SYSTEM.search_records(query, k=limit)
    except Exception:
        return []


def _duckduckgo_search_records(query: str, count: int = 8) -> list[dict]:
    """DuckDuckGo 免费网页搜索（无需 API Key）。"""
    records: list[dict] = []
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=count))
        for idx, r in enumerate(results, 1):
            records.append({
                "source_id": f"DDG-{idx}",
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
                "domain": _extract_domain(r.get("href", "")),
                "source_type": "web",
                "published_at": "",
            })
        logger.info("[duckduckgo] 搜索完成 | query=%s | 结果=%s", query[:40], len(records))
    except ImportError:
        logger.warning("[duckduckgo] 未安装 duckduckgo_search，跳过。安装: pip install duckduckgo-search")
    except Exception as e:
        logger.warning("[duckduckgo] 搜索失败: %s", e)
    return records


def _extract_domain(url: str) -> str:
    """从 URL 提取域名。"""
    if "://" in url:
        return url.split("://", 1)[1].split("/", 1)[0]
    return ""


def bocha_web_search_records(query: str, count: int = 8) -> list[dict]:
    api_key = os.getenv("BOCHA_API_KEY", "").strip()
    logger.info("[web_search] 开始搜索 | query=%s | count=%s", query, count)

    if not api_key:
        # Bocha 没配 → 降级到免费的 DuckDuckGo
        logger.info("[web_search] BOCHA_API_KEY 未配置，使用 DuckDuckGo 免费搜索")
        return _duckduckgo_search_records(query, count)
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
        domain = _extract_domain(url)
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


# ═══════════════════════════════════════════════════════════════════
# AKShare 金融数据工具（免费，无需 API Key）
# ═══════════════════════════════════════════════════════════════════

_AKSHARE_AVAILABLE = False
try:
    import akshare as ak
    _AKSHARE_AVAILABLE = True
    logger.info("[finance] AKShare 已加载，金融数据工具可用")
except ImportError:
    logger.warning("[finance] AKShare 未安装，金融数据工具降级为 stub。安装: pip install akshare")


def _safe_finance_call(func, *args, **kwargs):
    """安全调用 AKShare 函数，失败时返回空/错误信息。"""
    if not _AKSHARE_AVAILABLE:
        return None, "AKShare 未安装，请执行: pip install akshare"
    try:
        result = func(*args, **kwargs)
        return result, None
    except Exception as exc:
        return None, f"金融数据获取失败: {exc}"


def _normalize_stock_code(code: str) -> str:
    """标准化股票代码：002594 -> sz002594, 600519 -> sh600519"""
    code = code.strip().replace(" ", "")
    if len(code) == 6 and code.isdigit():
        if code.startswith(("0", "3")):
            return f"sz{code}"
        elif code.startswith(("6", "9")):
            return f"sh{code}"
        else:
            return f"sz{code}"
    return code


def _detect_stock_code(query: str) -> str | None:
    """从用户查询中尝试提取股票代码。"""
    import re
    # 匹配 6 位数字代码
    match = re.search(r'(?<!\d)(\d{6})(?!\d)', query)
    if match:
        return _normalize_stock_code(match.group(1))
    # 匹配常见股票简称？暂不实现，由 LLM 在 plan 阶段提取
    return None


# ── 工具 1: 股票历史行情 ──

def fetch_stock_price_records(
    symbol: str, period: str = "monthly", count: int = 24
) -> list[dict]:
    """获取股票历史行情数据，返回结构化记录列表。

    Args:
        symbol: 股票代码（6位数字如 002594，或带前缀如 sz002594）
        period: daily|weekly|monthly
        count: 返回最近多少条
    """
    records: list[dict] = []
    code = _normalize_stock_code(symbol)
    result, error = _safe_finance_call(
        ak.stock_zh_a_hist,
        symbol=code,
        period=period,
        adjust="qfq",
    )
    if error or result is None:
        return [{"error": error}]
    try:
        df = result.tail(count)
        for _, row in df.iterrows():
            date_str = str(row.get("日期", ""))
            close_val = float(row.get("收盘", 0))
            records.append({
                "source_id": f"FIN-PRICE-{len(records)+1}",
                "title": f"股价行情 {code} {date_str} 收盘{close_val:.2f}",
                "snippet": (
                    f"日期:{date_str} 开:{float(row.get('开盘',0)):.2f} "
                    f"收:{close_val:.2f} 高:{float(row.get('最高',0)):.2f} "
                    f"低:{float(row.get('最低',0)):.2f} 量:{int(row.get('成交量',0))}"
                ),
                "url": "",
                "date": date_str,
                "source_type": "finance_data",
                "data_type": "price_history",
            })
    except Exception as e:
        return [{"error": f"行情数据解析失败: {e}"}]
    return records


# ── 工具 2: 个股信息查询（含 PE/PB/市值等估值指标） ──

def fetch_stock_info_record(symbol: str) -> dict | None:
    """获取个股基本信息（含PE、PB、总市值、行业等）。

    Args:
        symbol: 标准化股票代码（如 sz002594）

    Returns:
        个股信息 dict，失败时返回 None
    """
    result, error = _safe_finance_call(ak.stock_individual_info_em, symbol=symbol)
    if error or result is None:
        logger.warning("[finance] 个股信息获取失败: %s", error)
        return None

    try:
        info: dict = {}
        for _, row in result.iterrows():
            key = str(row.get("item", ""))
            value = str(row.get("value", ""))
            info[key] = value

        # 提取关键估值指标
        pe_val = float(info.get("市盈率-动态", 0) or 0)
        pb_val = float(info.get("市净率", 0) or 0)
        total_mv = info.get("总市值", "")
        name = info.get("股票简称", "")

        return {
            "name": name,
            "pe": pe_val,
            "pb": pb_val,
            "total_mv": total_mv,
            "industry": info.get("行业", ""),
            "listing_date": info.get("上市时间", ""),
            "total_shares": info.get("总股本", ""),
        }
    except Exception as e:
        logger.warning("[finance] 个股信息解析失败: %s", e)
        return None


# ── 工具 3: 财务指标（同花顺数据源，免费） ──

def fetch_financial_indicators_records(stock_code: str) -> list[dict]:
    """获取股票财务指标（同花顺数据源：ROE、毛利率、净利率、营收增速、净利润增速等）。"""
    records: list[dict] = []
    raw_code = _normalize_stock_code(stock_code)
    short_code = raw_code[2:] if raw_code.startswith(("sz", "sh")) else raw_code

    result, error = _safe_finance_call(
        ak.stock_financial_abstract_ths, symbol=short_code, indicator="按报告期"
    )
    if error or result is None:
        return [{"error": error}]
    try:
        df = result.tail(8)  # 最近8个报告期
        for _, row in df.iterrows():
            report_date = str(row.get("报告期", ""))
            roe = _parse_pct(row.get("净资产收益率", ""))
            gross = _parse_pct(row.get("销售毛利率", ""))
            net = _parse_pct(row.get("销售净利率", ""))
            revenue_growth = _parse_pct(row.get("营业总收入同比增长率", ""))
            profit_growth = _parse_pct(row.get("净利润同比增长率", ""))
            debt = _parse_pct(row.get("资产负债率", ""))
            eps = str(row.get("基本每股收益", ""))
            bvps = str(row.get("每股净资产", ""))

            records.append({
                "source_id": f"FIN-IND-{len(records)+1}",
                "title": f"财务指标 {report_date} ROE={roe:.1f}% 毛利率={gross:.1f}%",
                "snippet": (
                    f"报告期:{report_date} | ROE:{roe:.1f}% | 毛利率:{gross:.1f}% | "
                    f"净利率:{net:.1f}% | 营收增速:{revenue_growth:.1f}% | "
                    f"利润增速:{profit_growth:.1f}% | 负债率:{debt:.1f}% | "
                    f"EPS:{eps} | 每股净资产:{bvps}"
                ),
                "url": "",
                "report_date": report_date,
                "source_type": "finance_data",
                "data_type": "financial_indicators",
            })
    except Exception as e:
        return [{"error": f"财务指标解析失败: {e}"}]
    return records


def _parse_pct(value) -> float:
    """解析百分比字符串，如 '40.85亿' -> 4085000000, '55.38%' -> 55.38, '-11.82%' -> -11.82"""
    import re
    text = str(value).strip()
    if not text or text == "None":
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass
    # 处理带后缀的数字
    match = re.match(r"([\-\d.,]+)\s*(亿|万|%)?", text)
    if match:
        num = float(match.group(1).replace(",", ""))
        unit = match.group(2)
        if unit == "亿":
            num *= 100000000
        elif unit == "万":
            num *= 10000
        return num
    return 0.0


# ── 工具 4: 股票新闻（东方财富，免费） ──

def fetch_stock_news_records(stock_code: str, limit: int = 10) -> list[dict]:
    """获取个股新闻（东方财富来源，免费无需 API Key）。"""
    records: list[dict] = []
    code = _normalize_stock_code(stock_code)
    result, error = _safe_finance_call(ak.stock_news_em, symbol=code)
    if error or result is None:
        return [{"error": error}]
    try:
        count = 0
        for _, row in result.iterrows():
            if count >= limit:
                break
            content_text = str(row.get("新闻内容", ""))[:300]
            records.append({
                "source_id": f"FIN-NEWS-{len(records)+1}",
                "title": str(row.get("新闻标题", "")),
                "url": str(row.get("新闻链接", "")),
                "snippet": content_text,
                "publish_time": str(row.get("发布时间", "")),
                "source_type": "finance_data",
                "data_type": "stock_news",
            })
            count += 1
    except Exception as e:
        return [{"error": f"新闻获取失败: {e}"}]
    return records


# ── 工具 5: 宏观指标 ──

def fetch_macro_indicator_records(indicator: str) -> list[dict]:
    """获取宏观经济指标。

    支持的 indicator: cpi | pmi | gdp | m2 | lpr | social_finance
    """
    records: list[dict] = []
    indicator_lower = indicator.lower().strip()

    try:
        if indicator_lower == "cpi":
            result, error = _safe_finance_call(ak.macro_china_cpi_yearly)
        elif indicator_lower == "pmi":
            result, error = _safe_finance_call(ak.macro_china_pmi_yearly)
        elif indicator_lower == "gdp":
            result, error = _safe_finance_call(ak.macro_china_gdp_yearly)
        elif indicator_lower == "m2":
            result, error = _safe_finance_call(ak.macro_china_money_supply)
        elif indicator_lower in ("lpr", "利率"):
            result, error = _safe_finance_call(ak.macro_china_lpr)
        elif indicator_lower in ("social_finance", "社融"):
            result, error = _safe_finance_call(ak.macro_china_shrzgm)
        else:
            return [{"error": f"不支持的宏观指标: {indicator}，支持: cpi/pmi/gdp/m2/lpr/social_finance"}]

        if error or result is None:
            return [{"error": error}]

        source_id_prefix = f"FIN-MACRO-{indicator_lower.upper()}"
        for idx, (_, row) in enumerate(result.tail(20).iterrows(), 1):
            date_str = str(row.iloc[0]) if len(row) > 0 else ""
            value_str = str(row.iloc[1]) if len(row) > 1 else ""
            records.append({
                "source_id": f"{source_id_prefix}-{idx}",
                "title": f"{indicator_lower.upper()} {date_str}: {value_str}",
                "snippet": f"日期:{date_str} | 指标:{indicator_lower.upper()} | 值:{value_str}",
                "url": "",
                "date": date_str,
                "value": value_str,
                "indicator": indicator_lower,
                "source_type": "finance_data",
                "data_type": "macro_indicator",
            })
    except Exception as e:
        return [{"error": f"宏观数据获取失败: {e}"}]
    return records


# ── 工具 6: 统一金融数据采集 ──

def collect_finance_data_records(query: str) -> list[dict]:
    """根据查询文本，自动采集相关金融数据并返回结构化记录列表。

    这是金融投研的主入口——从用户查询中提取股票代码，
    并行获取行情、财务指标、新闻，整合为统一的 evidence records。
    """
    all_records: list[dict] = []
    stock_code = _detect_stock_code(query)

    if not stock_code:
        # 检查是否涉及宏观指标
        macro_keywords = {
            "cpi": "cpi", "CPI": "cpi", "通胀": "cpi", "物价": "cpi",
            "pmi": "pmi", "PMI": "pmi", "采购经理": "pmi",
            "gdp": "gdp", "GDP": "gdp", "经济增长": "gdp",
            "m2": "m2", "M2": "m2", "货币供应": "m2",
            "lpr": "lpr", "LPR": "lpr", "利率": "lpr", "贷款市场": "lpr",
            "社融": "social_finance", "社会融资": "social_finance",
        }
        for keyword, indicator in macro_keywords.items():
            if keyword in query:
                macro_records = fetch_macro_indicator_records(indicator)
                all_records.extend(macro_records)
                break
        return all_records

    logger.info("[finance] 检测到股票代码: %s", stock_code)

    # 获取个股信息（PE/PB/市值等）
    info = fetch_stock_info_record(stock_code)
    short_code = stock_code[2:] if stock_code.startswith(("sz", "sh")) else stock_code
    if info:
        name = info.get("name", "")
        pe = info.get("pe", 0)
        pb = info.get("pb", 0)
        mv = info.get("total_mv", "")
        all_records.append({
            "source_id": "FIN-INFO-1",
            "name": name,
            "url": f"https://quote.eastmoney.com/{short_code}.html",
            "snippet": (
                f"{name} | PE:{pe:.2f} | PB:{pb:.2f} | 总市值:{mv} | "
                f"行业:{info.get('industry', '')} | 上市日期:{info.get('listing_date', '')}"
            ),
            "title": f"{name} 公司信息 PE={pe:.2f} PB={pb:.2f} 市值={mv}",
            "domain": "eastmoney",
            "reliability_hint": "data_provider",
            "source_type": "finance_data",
            "data_type": "company_info",
        })

    # 获取财务指标（同花顺数据源）
    fin_records = fetch_financial_indicators_records(stock_code)
    if fin_records and "error" not in fin_records[0]:
        for record in fin_records:
            record["domain"] = "10jqka.com.cn"
            record["reliability_hint"] = "data_provider"
        all_records.extend(fin_records[:8])

    # 获取新闻
    news_records = fetch_stock_news_records(stock_code, limit=8)
    if news_records and "error" not in news_records[0]:
        for record in news_records:
            record["domain"] = "eastmoney"
            record["reliability_hint"] = "media"
        all_records.extend(news_records)

    logger.info("[finance] 金融数据采集完成 | 总记录数=%s", len(all_records))
    return all_records
