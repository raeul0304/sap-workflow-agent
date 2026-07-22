from fastapi import FastAPI, HTTPException
from app.workflow.task_catalog import task_catalog

app = FastAPI()

@app.get("/api/task-types")
def get_task_types():
    return task_catalog.list_all()


@app.get("/api/task-types/{task_type:path}")
def get_task_type(task_type:str):
    return task_catalog.get(task_type)