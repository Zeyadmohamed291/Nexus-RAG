import logging
from celery_app import celery_app, get_setup_utils
from utils.idempotency_manager import IdempotencyManager
from utils.async_runner import safe_async_run

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.maintenance.clean_celery_executions_table",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
def clean_celery_executions_table(self):
    """Periodic Celery maintenance task to prune old idempotency execution records."""
    return safe_async_run(_clean_celery_executions_table(self))


async def _clean_celery_executions_table(task_instance):
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
        logger.info("Executing maintenance: cleaning expired Celery execution records")
        await idempotency_manager.cleanup_old_tasks(days=5)
        return True

    except Exception as e:
        logger.error(f"Maintenance task failed: {str(e)}")
        raise
    finally:
        try:
            if db_engine:
                await db_engine.dispose()
            if vectordb_client:
                await vectordb_client.disconnect()
        except Exception as e:
            logger.error(f"Error releasing resources in maintenance task: {str(e)}")