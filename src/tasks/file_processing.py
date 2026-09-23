import logging
from typing import Optional, Union, Dict, Any

from celery_app import celery_app, get_setup_utils
from helpers.config import get_settings
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from models.AssetModel import AssetModel
from models.db_schemes import DataChunk
from models import ResponseSignal
from models.enums.AssetTypeEnum import AssetTypeEnum
from controllers import ProcessController, NLPController
from utils.idempotency_manager import IdempotencyManager
from utils.async_runner import safe_async_run

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.file_processing.process_project_files",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
def process_project_files(
    self,
    project_id: int,
    file_id: Optional[Union[str, int]],
    chunk_size: int,
    overlap_size: int,
    do_reset: int
):
    """
    Celery task to load files, chunk content with sliding windows, and store chunks in the relational DB.
    Guarded by database-backed idempotency to prevent duplicate task execution.
    """
    return safe_async_run(
        _process_project_files(self, project_id, file_id, chunk_size, overlap_size, do_reset)
    )


async def _process_project_files(
    task_instance,
    project_id: int,
    file_id: Optional[Union[str, int]],
    chunk_size: int,
    overlap_size: int,
    do_reset: int
) -> Dict[str, Any]:
    db_engine, vectordb_client = None, None

    try:
        (
            db_engine,
            db_client,
            llm_provider_factory,
            vectordb_provider_factory,
            generation_client,
            embedding_client,
            vectordb_client,
            template_parser
        ) = await get_setup_utils()

        idempotency_manager = IdempotencyManager(db_client, db_engine)
        settings = get_settings()

        task_name = "tasks.file_processing.process_project_files"
        task_args = {
            "project_id": project_id,
            "file_id": file_id,
            "chunk_size": chunk_size,
            "overlap_size": overlap_size,
            "do_reset": do_reset
        }

        should_execute, existing_task = await idempotency_manager.should_execute_task(
            task_name=task_name,
            task_args=task_args,
            celery_task_id=task_instance.request.id,
            task_time_limit=settings.CELERY_TASK_TIME_LIMIT
        )

        if not should_execute:
            logger.info(f"Task already handled or in progress | status: {existing_task.status}")
            return existing_task.result or {}

        if existing_task:
            await idempotency_manager.update_task_status(
                execution_id=existing_task.execution_id,
                status="PENDING"
            )
            task_record = existing_task
        else:
            task_record = await idempotency_manager.create_task_record(
                task_name=task_name,
                task_args=task_args,
                celery_task_id=task_instance.request.id
            )

        await idempotency_manager.update_task_status(
            execution_id=task_record.execution_id,
            status="STARTED"
        )

        project_model = await ProjectModel.create_instance(db_client=db_client)
        project = await project_model.get_project_or_create_one(project_id=project_id)

        nlp_controller = NLPController(
            vectordb_client=vectordb_client,
            generation_client=generation_client,
            embedding_client=embedding_client,
            template_parser=template_parser,
        )

        asset_model = await AssetModel.create_instance(db_client=db_client)
        project_files_ids: Dict[int, str] = {}

        if file_id:
            asset_record = await asset_model.get_asset_record(
                asset_project_id=project.project_id,
                asset_name=str(file_id)
            )

            if asset_record is None:
                err_signal = ResponseSignal.FILE_ID_ERROR.value
                task_instance.update_state(state="FAILURE", meta={"signal": err_signal})
                await idempotency_manager.update_task_status(
                    execution_id=task_record.execution_id,
                    status="FAILURE",
                    result={"signal": err_signal}
                )
                raise FileNotFoundError(f"No asset found for file: {file_id}")

            project_files_ids = {asset_record.asset_id: asset_record.asset_name}
        else:
            project_files = await asset_model.get_all_project_assets(
                asset_project_id=project.project_id,
                asset_type=AssetTypeEnum.FILE.value,
            )
            project_files_ids = {record.asset_id: record.asset_name for record in project_files}

        if not project_files_ids:
            no_files_signal = ResponseSignal.NO_FILES_ERROR.value
            task_instance.update_state(state="FAILURE", meta={"signal": no_files_signal})
            await idempotency_manager.update_task_status(
                execution_id=task_record.execution_id,
                status="FAILURE",
                result={"signal": no_files_signal}
            )
            raise FileNotFoundError(f"No files found for project_id: {project.project_id}")

        process_controller = ProcessController(project_id=project_id)
        chunk_model = await ChunkModel.create_instance(db_client=db_client)

        if do_reset == 1:
            collection_name = nlp_controller.create_collection_name(project_id=project.project_id)
            await vectordb_client.delete_collection(collection_name=collection_name)
            await chunk_model.delete_chunks_by_project_id(project_id=project.project_id)

        total_inserted_chunks = 0
        total_processed_files = 0

        for asset_id, current_file_id in project_files_ids.items():
            file_content = process_controller.get_file_content(file_id=current_file_id)
            if not file_content:
                logger.error(f"Could not load content for file: {current_file_id}")
                continue

            file_chunks = process_controller.process_file_content(
                file_content=file_content,
                file_id=current_file_id,
                chunk_size=chunk_size,
                overlap_size=overlap_size
            )

            if not file_chunks:
                logger.warning(f"No chunks extracted from file: {current_file_id}")
                continue

            chunk_records = [
                DataChunk(
                    chunk_text=chunk.page_content,
                    chunk_metadata=chunk.metadata,
                    chunk_order=idx + 1,
                    chunk_project_id=project.project_id,
                    chunk_asset_id=asset_id
                )
                for idx, chunk in enumerate(file_chunks)
            ]

            total_inserted_chunks += await chunk_model.insert_many_chunks(chunks=chunk_records)
            total_processed_files += 1

        success_result = {
            "signal": ResponseSignal.PROCESSING_SUCCESS.value,
            "inserted_chunks": total_inserted_chunks,
            "processed_files": total_processed_files,
            "project_id": project_id,
            "do_reset": do_reset
        }

        task_instance.update_state(
            state="SUCCESS",
            meta={"signal": ResponseSignal.PROCESSING_SUCCESS.value}
        )

        await idempotency_manager.update_task_status(
            execution_id=task_record.execution_id,
            status="SUCCESS",
            result=success_result
        )

        return success_result

    except Exception as e:
        logger.error(f"File processing task failed: {str(e)}")
        raise
    finally:
        try:
            if db_engine:
                await db_engine.dispose()
            if vectordb_client:
                await vectordb_client.disconnect()
        except Exception as e:
            logger.error(f"Error releasing resources in file processing task: {str(e)}")