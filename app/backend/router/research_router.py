import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.schemas import ResearchRequest, ResearchResponse
from backend.service import WorkflowService, get_workflow_service


router = APIRouter(prefix="/api/v1/research", tags=["research"])


@router.post("/run", response_model=ResearchResponse)
async def run_research(
    payload: ResearchRequest,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> ResearchResponse:
    final = await workflow_service.run(
        query=payload.query,
        user_id=payload.user_id,
        thread_id=payload.thread_id,
        tenant_id=payload.tenant_id,
        max_iterations=payload.max_iterations,
        enable_memory=payload.enable_memory,
    )
    return ResearchResponse(
        query=payload.query,
        user_id=payload.user_id,
        thread_id=payload.thread_id,
        tenant_id=payload.tenant_id,
        final=final,
    )


@router.post("/stream")
async def stream_research(
    payload: ResearchRequest,
    workflow_service: WorkflowService = Depends(get_workflow_service),
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
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
