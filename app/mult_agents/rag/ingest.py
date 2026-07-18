"""金融知识库文档入库脚本。

用法：
    python -m mult_agents.rag.ingest /path/to/docs
    python -m mult_agents.rag.ingest /path/to/docs --collection finance_knowledge
    python -m mult_agents.rag.ingest /path/to/report.pdf --chunk-size 800

支持的格式：.txt .md .pdf（需 pip install pypdf）
"""

import argparse
import logging
import sys
from pathlib import Path

# 确保 mult_agents 包可导入
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from mult_agents.config import AppConfig
from mult_agents.rag.core import RAGSystem, RAGConfig


def _collect_files(input_path: Path) -> list[Path]:
    """递归收集支持的文件。"""
    if input_path.is_file():
        return [input_path]

    extensions = {".txt", ".md", ".markdown"}
    try:
        import pypdf
        extensions.add(".pdf")
    except ImportError:
        pass

    files: list[Path] = []
    for ext in extensions:
        files.extend(input_path.rglob(f"*{ext}"))
    return sorted(files)


def _read_file(path: Path) -> str:
    """读取文件内容，支持 txt/md/pdf。"""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        except ImportError:
            raise RuntimeError("PDF 需要 pypdf 库: pip install pypdf")
    return path.read_text(encoding="utf-8", errors="replace")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logger = logging.getLogger("ingest")

    parser = argparse.ArgumentParser(description="金融文档入库")
    parser.add_argument("input", type=str, help="文档路径（文件或目录）")
    parser.add_argument("--collection", type=str, default=None, help="Milvus 集合名（默认读取 config.json）")
    parser.add_argument("--chunk-size", type=int, default=500, help="分块大小（默认 500）")
    parser.add_argument("--chunk-overlap", type=int, default=50, help="分块重叠（默认 50）")
    args = parser.parse_args()

    # 加载配置
    config = AppConfig.from_file()

    collection = args.collection or config.milvus_collection
    if collection == "mult_agent_memory":
        collection = "mult_agent_knowledge"  # 知识库用独立集合，避免与记忆系统混用

    rag_config = RAGConfig(
        milvus_host=config.milvus_host or "127.0.0.1",
        milvus_port=config.milvus_port,
        collection_name=collection,
        embedding_provider=config.embedding_provider,
        embedding_api_key=config.embedding_api_key,
        embedding_model=config.embedding_model,
        embedding_base_url=config.embedding_base_url,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"路径不存在: {input_path}")
        sys.exit(1)

    files = _collect_files(input_path)
    if not files:
        print(f"未找到支持的文档（.txt/.md/.pdf）: {input_path}")
        sys.exit(1)

    print(f"待入库文件: {len(files)} 个")
    print(f"目标集合:   {collection}")
    print(f"嵌入模型:   {config.embedding_provider}/{config.embedding_model}")
    print(f"分块大小:   {args.chunk_size}")
    print()

    rag = RAGSystem(config=rag_config)
    total_chunks = 0
    for idx, file_path in enumerate(files, 1):
        try:
            text = _read_file(file_path)
            chunks = rag.ingest_text(text, source=str(file_path))
            total_chunks += chunks
            rel_path = file_path.relative_to(input_path.parent) if input_path.is_file() else file_path.relative_to(input_path)
            print(f"  [{idx}/{len(files)}] {rel_path} → {chunks} chunks")
        except Exception as e:
            logger.warning("跳过 %s: %s", file_path.name, e)

    print(f"\n入库完成: {len(files)} 个文件, {total_chunks} 个 chunk, collection={collection}")
    print(f"\n确认 config.json 中 milvus_collection 设为 \"{collection}\"")
    print("（或在 .env 中设置 MILVUS_COLLECTION=finance_knowledge）")


if __name__ == "__main__":
    main()
