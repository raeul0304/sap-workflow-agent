from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.workflow.task_catalog import task_catalog
from app.workflow.schemas import ProcessApplyResponseData, ProcessApplyRequest, ProcessApplyResponse
from app.workflow.spiff_engine import SpiffEngine, run_workflow
from app.workflow.registry import WorkflowRegistry
from app.workflow.events import event_manager

app = FastAPI()

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

@app.post("/api/process/apply", response_model=ProcessApplyResponse)
async def apply_process(request: ProcessApplyRequest, background_tasks: BackgroundTasks):
    """BPMN 배포 후 즉시 응답을 주고, 워크플로 실행은 백그라운드에서 진행"""

    try:
        target_process_id = "Process_1"
        target_workflow_type = "test_workflow_type_1"

        # Admin 역할 - DB에서 불러왔거나 프론트에서 받은 XML 문자열로 엔진 생성
        engine = SpiffEngine(bpmn_xml=request.xml, process_id=target_process_id)
        workflow_registry.register(target_workflow_type, engine, force=True)

        # 백그라운드 태스크로 엔진 실행을 넘김
        background_tasks.add_task(
            run_workflow,
            registry=workflow_registry,
            workflow_type=target_workflow_type,
            requester_id=TEMP_REQUESTER_ID,
            requester_roles=TEMP_REQUESTER_ROLES
        )

        return ProcessApplyResponse(
            code="Sucess",
            message="Process applied and execution started.",
            data=ProcessApplyResponseData(status="Initializing")
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"프로세스 배포 및 실행 중 오류 발생 : {str(e)}")


@app.get("/api/process/stream/{workflow_id}")
async def stream_workflow_events(workflow_id: str):
    """프론트엔드에서 실시간으로 엔진 실행 상태를 수신하는 SSE 엔드포인트"""

    async def event_generator():
        # 이벤트를 받을 비동기 큐 구독
        queue = event_manager.subscribe(workflow_id)
        try:
            while True:
                # 큐에 이벤트가 들어올 때까지 대기
                event_data = await queue.get()

                # SSE 표준 포맷으로 변환하여 프론트엔드로 전송
                yield f"data: {event_data}\n\n"

                # 워크플로가 끝나거나 대기 상태에 빠지면 스트림 종료
                if "WORKFLOW_STATUS_UPDATE" in event_data:
                    break

        finally:
            event_manager.unsubscribe(workflow_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")