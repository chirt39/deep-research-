"""报告历史存储：JSONL 追加写，支持列表与详情查询（线程安全）。"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "reports.jsonl"


class ReportStore:
    def __init__(self, path: str | Path | None = None):
        self._path = Path(path) if path else _DEFAULT_PATH
        self._lock = threading.Lock()

    def save(self, report: dict) -> str:
        report_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
        entry = {
            "id": report_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **report,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return report_id

    def list_reports(self, limit: int = 50) -> list[dict]:
        """返回最近 limit 条报告的元信息（不含正文）。"""
        if not self._path.exists():
            return []
        reports = []
        with self._lock:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                reports.append(
                    {
                        "id": item.get("id"),
                        "query": item.get("query", ""),
                        "thread_id": item.get("thread_id", ""),
                        "user_id": item.get("user_id", ""),
                        "created_at": item.get("created_at", ""),
                        "usage": item.get("usage", {}),
                        "quality": item.get("quality", {}),
                        "research_domain": item.get("research_domain", "general"),
                        "evidence_summary": item.get("evidence_summary", {}),
                    }
                )
        return list(reversed(reports[-limit:]))

    def get_report(self, report_id: str) -> dict | None:
        if not self._path.exists():
            return None
        with self._lock:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("id") == report_id:
                    return item
        return None
