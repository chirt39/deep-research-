from functools import lru_cache

from ..config import AppSettings
from ..report_store import ReportStore
from .workflow_service import WorkflowService


@lru_cache(maxsize=1)
def get_workflow_service() -> WorkflowService:
    settings = AppSettings()
    return WorkflowService(config_path=settings.config_path)


@lru_cache(maxsize=1)
def get_report_store() -> ReportStore:
    return ReportStore()


__all__ = ["WorkflowService", "get_workflow_service", "ReportStore", "get_report_store"]
