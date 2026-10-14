import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..report_store import ReportStore
from ..schemas import ResearchRequest, ResearchResponse
from ..security import require_auth
from ..service import WorkflowService, get_report_store, get_workflow_service


router = APIRouter(prefix="/api/v1/research", tags=["research"])


@router.get("/history")
async def list_history(
    limit: int = 50,
    _: None = Depends(require_auth),
    store: ReportStore = Depends(get_report_store),
) -> dict:
    return {"reports": store.list_reports(limit=min(max(limit, 1), 100))}


@router.get("/history/{report_id}")
async def get_history(
    report_id: str,
    _: None = Depends(require_auth),
    store: ReportStore = Depends(get_report_store),
) -> dict:
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


@router.post("/run", response_model=ResearchResponse)
async def run_research(
    payload: ResearchRequest,
    workflow_service: WorkflowService = Depends(get_workflow_service),
    _: None = Depends(require_auth),
) -> ResearchResponse:
    final, route, usage, quality, meta = await workflow_service.run_with_meta(
        query=payload.query,
        user_id=payload.user_id,
        thread_id=payload.thread_id,
        tenant_id=payload.tenant_id,
        max_iterations=payload.max_iterations,
        enable_memory=payload.enable_memory,
        research_domain=payload.research_domain,
    )
    return ResearchResponse(
        query=payload.query,
        user_id=payload.user_id,
        thread_id=payload.thread_id,
        tenant_id=payload.tenant_id,
        final=final,
        usage=usage,
        quality=quality,
        report_id=meta.get("report_id"),
        research_domain=meta.get("research_domain", payload.research_domain),
        evidence_summary=meta.get("evidence_summary"),
        trace=meta.get("trace", []),
    )


@router.post("/stream")
async def stream_research(
    payload: ResearchRequest,
    workflow_service: WorkflowService = Depends(get_workflow_service),
    _: None = Depends(require_auth),
) -> StreamingResponse:
    async def event_stream():
        start_event = {"type": "status", "message": "任务已接收，正在初始化多智能体链路"}
        yield f"data: {json.dumps(start_event, ensure_ascii=False)}\n\n"
        async for event in workflow_service.stream_events(
            query=payload.query,
            user_id=payload.user_id,
            thread_id=payload.thread_id,
            tenant_id=payload.tenant_id,
            max_iterations=payload.max_iterations,
            enable_memory=payload.enable_memory,
            research_domain=payload.research_domain,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
