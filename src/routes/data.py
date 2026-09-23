import os
import logging
import aiofiles
from fastapi import APIRouter, Depends, UploadFile, status, Request
from fastapi.responses import JSONResponse

from helpers.config import get_settings, Settings
from controllers import DataController, ProjectController
from models import ResponseSignal
from models.ProjectModel import ProjectModel
from models.AssetModel import AssetModel
from models.db_schemes import Asset
from models.enums.AssetTypeEnum import AssetTypeEnum
from tasks.file_processing import process_project_files
from tasks.process_workflow import process_and_push_workflow
from .schemes.data import ProcessRequest

logger = logging.getLogger("uvicorn.error")

data_router = APIRouter(
    prefix="/api/v1/data",
    tags=["Data & Ingestion"],
)


@data_router.post("/upload/{project_id}")
async def upload_data(
    request: Request,
    project_id: int,
    file: UploadFile,
    app_settings: Settings = Depends(get_settings)
):
    """
    Upload and validate a document (PDF / TXT) for ingestion into a project workspace.
    """
    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_or_create_one(project_id=project_id)

    data_controller = DataController()
    is_valid, result_signal = data_controller.validate_uploaded_file(file=file)

    if not is_valid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": result_signal}
        )

    file_path, file_id = data_controller.generate_unique_filepath(
        orig_file_name=file.filename,
        project_id=project_id
    )

    try:
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                await f.write(chunk)
    except Exception as e:
        logger.error(f"Error while uploading file {file.filename}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": ResponseSignal.FILE_UPLOAD_FAILED.value}
        )

    # Persist asset record in the database
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    asset_resource = Asset(
        asset_project_id=project.project_id,
        asset_type=AssetTypeEnum.FILE.value,
        asset_name=file_id,
        asset_size=os.path.getsize(file_path)
    )
    asset_record = await asset_model.create_asset(asset=asset_resource)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "signal": ResponseSignal.FILE_UPLOAD_SUCCESS.value,
            "file_id": str(asset_record.asset_id),
            "file_name": file_id
        }
    )


@data_router.post("/process/{project_id}")
async def process_endpoint(request: Request, project_id: int, process_request: ProcessRequest):
    """
    Trigger an asynchronous Celery task to chunk uploaded project files and persist them into the relational DB.
    """
    task = process_project_files.delay(
        project_id=project_id,
        file_id=process_request.file_id,
        chunk_size=process_request.chunk_size,
        overlap_size=process_request.overlap_size,
        do_reset=process_request.do_reset,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "signal": ResponseSignal.PROCESSING_SUCCESS.value,
            "task_id": task.id
        }
    )


@data_router.post("/process-and-push/{project_id}")
async def process_and_push_endpoint(request: Request, project_id: int, process_request: ProcessRequest):
    """
    Trigger end-to-end asynchronous pipeline: chunk files AND index embeddings into vector store.
    """
    workflow_task = process_and_push_workflow.delay(
        project_id=project_id,
        file_id=process_request.file_id,
        chunk_size=process_request.chunk_size,
        overlap_size=process_request.overlap_size,
        do_reset=process_request.do_reset,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "signal": ResponseSignal.PROCESS_AND_PUSH_WORKFLOW_READY.value,
            "workflow_task_id": workflow_task.id
        }
    )
