from fastapi import FastAPI, HTTPException
from app.workflow.task_catalog import task_catalog

app = FastAPI()

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