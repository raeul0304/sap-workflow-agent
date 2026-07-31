import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import (
    BackgroundTasks,
    FastAPI,
    Header,
    HTTPException,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.workflow.events import event_manager
from app.workflow.registry import WorkflowRegistry
from app.workflow.schemas import (
    ProcessApplyRequest,
    ProcessApplyResponse,
    ProcessApplyResponseData,
)
from app.workflow.spiff_engine import (
    SpiffEngine,
    run_workflow,
    run_created_workflow,
)
from app.workflow.task_catalog import task_catalog



@asynccontextmanager
async def lifespan(app: FastAPI):
    event_manager.set_event_loop(asyncio.get_running_loop())
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 주소(프론트엔드)에서의 접근 허용
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, OPTIONS 등 모든 통신 방식 허용
    allow_headers=["*"],  # 모든 헤더 허용
)


workflow_registry = WorkflowRegistry() # 실제 가동 시 DB에서 기존 등록된 워크플로를 꺼내와 여기에 적재


@app.get("/api/task-types")
def get_task_types():
    task_types = task_catalog.list_all()

    if task_types is None:
        raise HTTPException(
            status_code=404,
            detail="등록된 Task 유형이 없습니다"
        )
    
    return task_types


@app.get("/api/task-types/{task_type:path}")
def get_task_type_fields(task_type:str):
    task_definition = task_catalog.get(task_type)

    if task_definition is None:
        raise HTTPException(
            status_code=404,
            detail=f"등록되지 않은 Task 유형입니다: {task_type}"
        )
    
    fields = task_definition.get("fields") or []        
    
    return fields



TEMP_REQUESTER_ID = "user-001"
TEMP_REQUESTER_ROLES = ["USER"]

@app.post(
    "/api/process/apply",
    response_model=ProcessApplyResponse,
)
async def apply_process(
    request: ProcessApplyRequest,
    background_tasks: BackgroundTasks,
):
    """BPMN을 등록하고 워크플로 ID를 반환한 뒤 백그라운드에서 실행."""

    try:
        target_process_id = "Process_1"
        target_workflow_type = "test_workflow_type_1"

        engine = SpiffEngine(
            bpmn_xml=request.xml,
            process_id=target_process_id,
        )

        workflow_registry.register(
            target_workflow_type,
            engine,
            force=True,
        )

        # 먼저 인스턴스를 생성하여 workflow_id 확보
        workflow_id = engine.create_instance(
            requester_id=TEMP_REQUESTER_ID,
            requester_roles=TEMP_REQUESTER_ROLES,
            initial_data=None,
        )

        # 이미 만든 인스턴스를 백그라운드에서 실행
        background_tasks.add_task(
            run_created_workflow,
            registry=workflow_registry,
            workflow_type=target_workflow_type,
            workflow_id=workflow_id,
        )

        return ProcessApplyResponse(
            code="Success",
            message="Process applied and execution started.",
            data=ProcessApplyResponseData(
                workflow_id=workflow_id,
                status="INITIALIZING",
                events_url=f"/api/process/stream/{workflow_id}",
            ),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"프로세스 배포 및 실행 중 오류 발생: {exc}",
        ) from exc



@app.get("/api/process/stream/{workflow_id}")
async def stream_workflow_events(
    workflow_id: str,
    request: Request,
    last_event_id: str | None = Header(
        default=None,
        alias="Last-Event-ID",
    ),
):
    """특정 워크플로 실행 이벤트를 SSE로 전달."""

    parsed_last_event_id: int | None = None

    if last_event_id:
        try:
            parsed_last_event_id = int(last_event_id)
        except ValueError:
            parsed_last_event_id = None

    async def event_generator():
        queue = event_manager.subscribe(
            workflow_id,
            last_event_id=parsed_last_event_id,
        )

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event_data = await asyncio.wait_for(
                        queue.get(),
                        timeout=15,
                    )

                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                event = json.loads(event_data)
                event_id = event["event_id"]
                event_type = event.get("event_type", "message")

                yield (
                    f"id: {event_id}\n"
                    f"event: {event_type}\n"
                    f"data: {event_data}\n\n"
                )

                if (
                    event.get("type") == "WORKFLOW_STATUS_UPDATE"
                    and event.get("status") in {"COMPLETED", "FAILED"}
                ):
                    break

        finally:
            event_manager.unsubscribe(
                workflow_id,
                queue,
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )