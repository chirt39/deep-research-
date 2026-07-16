import logging
import os
import sys
from pathlib import Path

from mult_agents.src.mult_agents.rag.core import RAGSystem
from mult_agents_memory.app.mult_agents.config import AppConfig
from mult_agents_memory.app.mult_agents.rag.core import RAGConfig

# 将项目根目录添加到 PYTHONPATH，解决模块导入问题
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 先加载 .env，再导入其他模块（确保 Milvus 配置正确）
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)






INPUT_PATH = Path("/Users/pengshaoyong/Documents/AI_Project/mult_agent/mult_agents_memory/README.md")
COLLECTION_NAME = ""
MILVUS_HOST = ""
MILVUS_PORT = 0
EMBEDDING_MODEL = "text-embedding-v1"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _collect_paths(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    patterns = ("*.txt", "*.md", "*.markdown")
    paths: list[Path] = []
    for pat in patterns:
        paths.extend(sorted(input_path.rglob(pat)))
    return paths


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    config = AppConfig.from_file()
    collection_name = COLLECTION_NAME or config.milvus_collection
    milvus_host = MILVUS_HOST or config.milvus_host
    milvus_port = MILVUS_PORT or config.milvus_port
    rag_cfg = RAGConfig(
        milvus_host=milvus_host,
        milvus_port=milvus_port,
        collection_name=collection_name,
        embedding_model=EMBEDDING_MODEL,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    rag = RAGSystem(api_key=config.api_key, config=rag_cfg)

    input_path = INPUT_PATH.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(str(input_path))

    paths = _collect_paths(input_path)
    if not paths:
        raise ValueError(f"未找到可入库文件: {input_path}")

    total_chunks = rag.ingest_paths(paths)
    print(f"入库完成 | 文件数={len(paths)} | chunk数={total_chunks} | collection={collection_name}")


if __name__ == "__main__":
    main()
