import logging
from typing import Optional, Union, Dict, Any
from celery import chain
from celery_app import celery_app
from tasks.file_processing import process_project_files
from tasks.data_indexing import _index_data_content
from utils.async_runner import safe_async_run

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.process_workflow.push_after_process_task",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
def push_after_process_task(self, prev_task_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chained pipeline task: automatically triggered after file processing completes to trigger vector indexing.
    """
    project_id = prev_task_result.get("project_id")
    do_reset = prev_task_result.get("do_reset", 0)

    task_results = safe_async_run(
        _index_data_content(self, project_id, do_reset)
    )

    return {
        "project_id": project_id,
        "do_reset": do_reset,
        "task_results": task_results
    }


@celery_app.task(
    bind=True,
    name="tasks.process_workflow.process_and_push_workflow",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
def process_and_push_workflow(
    self,
    project_id: int,
    file_id: Optional[Union[str, int]],
    chunk_size: int,
    overlap_size: int,
    do_reset: int
) -> Dict[str, Any]:
    """
    Composite asynchronous workflow:
    1. Parse and chunk project files into the relational database.
    2. Sequentially index generated chunks into the vector store.
    """
    if celery_app.conf.task_always_eager:
        res1 = process_project_files.apply(
            args=[project_id, file_id, chunk_size, overlap_size, do_reset]
        ).get()
        res2 = push_after_process_task.apply(args=[res1]).get()
        return {
            "signal": "WORKFLOW_COMPLETED",
            "workflow_id": str(self.request.id) if self.request and self.request.id else "local-sync",
            "result": res2
        }

    workflow = chain(
        process_project_files.s(project_id, file_id, chunk_size, overlap_size, do_reset),
        push_after_process_task.s()
    )

    result = workflow.apply_async()

    return {
        "signal": "WORKFLOW_STARTED",
        "workflow_id": result.id,
        "tasks": [
            "tasks.file_processing.process_project_files",
            "tasks.process_workflow.push_after_process_task"
        ]
    }
