"""轻量 token / 成本估算：用于统计每次研究的 LLM 开销。

价格默认按 DeepSeek deepseek-chat 公开报价（元 / 百万 token）估算，
可用环境变量覆盖：DEEPSEEK_INPUT_PRICE_PER_M / DEEPSEEK_OUTPUT_PRICE_PER_M。
"""

import math
import os
from typing import Iterable


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF  # 中日韩统一表意文字
        or 0x3400 <= code <= 0x4DBF  # 扩展 A
        or 0x3000 <= code <= 0x303F  # CJK 标点
    )


def estimate_tokens(text: str) -> int:
    """按字符启发式估算 token 数：中文约 0.7 token/字，英文/数字约 0.25 token/字符。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = max(len(text) - cjk, 0)
    return max(1, math.ceil(cjk * 0.7 + other * 0.25))


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """估算单次调用的成本（元）。"""
    input_price = float(os.getenv("DEEPSEEK_INPUT_PRICE_PER_M", "1"))
    output_price = float(os.getenv("DEEPSEEK_OUTPUT_PRICE_PER_M", "2"))
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)


def aggregate_usage(usage_log: Iterable[dict]) -> dict:
    """汇总一次研究的所有 LLM 调用用量。"""
    entries = list(usage_log or [])
    return {
        "calls": len(entries),
        "input_tokens": sum(int(item.get("input_tokens", 0)) for item in entries),
        "output_tokens": sum(int(item.get("output_tokens", 0)) for item in entries),
        "cost_yuan": round(sum(float(item.get("cost_yuan", 0)) for item in entries), 4),
        "elapsed_seconds": round(sum(float(item.get("elapsed_seconds", 0)) for item in entries), 1),
    }
