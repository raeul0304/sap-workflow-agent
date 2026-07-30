from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.workflow.task_catalog import task_catalog
from app.workflow.schemas import ProcessApplyResponseData, ProcessApplyRequest, ProcessApplyResponse
from app.workflow.spiff_engine import SpiffEngine, run_workflow
from app.workflow.registry import WorkflowRegistry

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
async def apply_process(request: ProcessApplyRequest):
    """프론트엔드로부터 BPMN XML을 전달받아 프로세스 실행을 시작"""

    try:
        target_process_id = "Process_1"
        target_workflow_type = "test_workflow_type_1"

        # 1. Admin 역할 - DB에서 불러왔거나 프론트에서 받은 XML 문자열로 엔진 생성
        engine = SpiffEngine(bpmn_xml=request.xml, process_id=target_process_id)
        workflow_registry.register(target_workflow_type, engine, force=True)

        # 2. End user - 실행 단계
        result = run_workflow(
            registry=workflow_registry,
            workflow_type=target_workflow_type,
            requester_id=TEMP_REQUESTER_ID,
            requester_roles=TEMP_REQUESTER_ROLES
        )

        return ProcessApplyResponse(
            code="Sucess",
            message="Process applied and execution started.",
            data=ProcessApplyResponseData(status=result.status.capitalize())
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"프로세스 배포 및 실행 중 오류 발생 : {str(e)}")
