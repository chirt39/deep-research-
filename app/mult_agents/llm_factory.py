"""LLM 工厂模块：统一创建 DeepSeek ChatOpenAI 实例和多后端嵌入模型。"""

import logging
import os
from typing import Optional

logger = logging.getLogger("mult_agents.llm_factory")

# ── 嵌入模型缓存 ──
_EMBEDDINGS_CACHE: Optional[object] = None
_EMBEDDINGS_CACHE_KEY: tuple = ()


def build_chat_model(
    model: str = "deepseek-chat",
    api_key: str = "",
    base_url: str = "https://api.deepseek.com/v1",
    temperature: float = 0.3,
):
    """创建 DeepSeek Chat 模型实例（OpenAI 兼容协议）。

    返回 langchain ChatOpenAI 实例。
    """
    from langchain_openai import ChatOpenAI

    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key or None,
        openai_api_base=base_url.rstrip("/") if base_url else "https://api.deepseek.com/v1",
        max_tokens=4096,
        timeout=45,
        max_retries=1,
    )


def build_summary_llm(
    model: str = "deepseek-chat",
    api_key: str = "",
    base_url: str = "https://api.deepseek.com/v1",
):
    """创建用于对话摘要的轻量 LLM（低温度）。"""
    return build_chat_model(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
    )


def build_embeddings(
    provider: str = "huggingface",
    api_key: str = "",
    model: str = "BAAI/bge-small-zh-v1.5",
    base_url: str = "",
    use_cache: bool = True,
):
    """多后端嵌入模型工厂。

    支持的 provider:
    - huggingface: 本地 sentence-transformers（无需 API Key，默认 BGE 中文模型）
    - openai: OpenAI / DeepSeek 兼容嵌入 API
    - dashscope: 阿里 DashScope 嵌入（text-embedding-v1/v2/v3）
    - local: 同 huggingface

    Args:
        provider: 后端类型
        api_key: API Key（openai/dashscope 需要）
        model: 模型名
        base_url: API 地址（openai 兼容时使用）
        use_cache: 是否复用已创建的嵌入实例（同一进程内）

    Returns:
        langchain Embeddings 实例
    """
    global _EMBEDDINGS_CACHE, _EMBEDDINGS_CACHE_KEY

    cache_key = (provider, api_key, model, base_url)
    if use_cache and _EMBEDDINGS_CACHE is not None and _EMBEDDINGS_CACHE_KEY == cache_key:
        return _EMBEDDINGS_CACHE

    embeddings = None
    provider_lower = provider.lower()

    # ── HuggingFace / local ──
    if provider_lower in ("huggingface", "local"):
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            embeddings = HuggingFaceEmbeddings(
                model_name=model or "BAAI/bge-small-zh-v1.5",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            logger.info("嵌入模型: HuggingFace | model=%s", model or "BAAI/bge-small-zh-v1.5")
        except ImportError:
            logger.error(
                "HuggingFace 嵌入需要 langchain-huggingface，请安装: "
                "pip install langchain-huggingface sentence-transformers"
            )
            raise

    # ── OpenAI 兼容 ──
    elif provider_lower == "openai":
        try:
            from langchain_openai import OpenAIEmbeddings
            kwargs = {
                "model": model or "text-embedding-3-small",
                "openai_api_key": api_key or None,
            }
            if base_url:
                kwargs["openai_api_base"] = base_url.rstrip("/")
            embeddings = OpenAIEmbeddings(**kwargs)
            logger.info("嵌入模型: OpenAI | model=%s | base_url=%s",
                        model or "text-embedding-3-small", base_url or "default")
        except ImportError:
            logger.error("OpenAI 嵌入需要 langchain-openai，请安装: pip install langchain-openai")
            raise

    # ── DashScope（阿里） ──
    elif provider_lower == "dashscope":
        try:
            from langchain_community.embeddings import DashScopeEmbeddings
            if api_key:
                os.environ.setdefault("DASHSCOPE_API_KEY", api_key)
            embeddings = DashScopeEmbeddings(
                model=model or "text-embedding-v1",
                dashscope_api_key=api_key or None,
            )
            logger.info("嵌入模型: DashScope | model=%s", model or "text-embedding-v1")
        except ImportError:
            logger.error("DashScope 嵌入需要 langchain-community，请安装: pip install langchain-community")
            raise

    else:
        raise ValueError(
            f"不支持的嵌入模型 provider: {provider}。可选: huggingface, openai, dashscope, local"
        )

    if use_cache:
        _EMBEDDINGS_CACHE = embeddings
        _EMBEDDINGS_CACHE_KEY = cache_key

    return embeddings


def clear_embeddings_cache():
    """清除嵌入模型缓存（配置变更后调用）。"""
    global _EMBEDDINGS_CACHE, _EMBEDDINGS_CACHE_KEY
    _EMBEDDINGS_CACHE = None
    _EMBEDDINGS_CACHE_KEY = ()
