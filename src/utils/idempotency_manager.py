import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, Dict, Any
from sqlalchemy import select, delete
from models.db_schemes.minirag.schemes.celery_task_execution import CeleryTaskExecution


class IdempotencyManager:
    """
    Manages database-backed task idempotency and execution status tracking.
    Prevents duplicate background processing and detects stuck jobs.
    """

    def __init__(self, db_client: Any, db_engine: Any) -> None:
        self.db_client = db_client
        self.db_engine = db_engine

    def create_args_hash(self, task_name: str, task_args: Dict[str, Any]) -> str:
        """Generate SHA-256 hash of task name and serialized arguments."""
        combined_data = {
            **task_args,
            "task_name": task_name
        }
        json_string = json.dumps(combined_data, sort_keys=True, default=str)
        return hashlib.sha256(json_string.encode()).hexdigest()

    async def create_task_record(
        self,
        task_name: str,
        task_args: Dict[str, Any],
        celery_task_id: Optional[str] = None
    ) -> CeleryTaskExecution:
        """Create a new task execution record."""
        args_hash = self.create_args_hash(task_name, task_args)

        now_utc = datetime.now(timezone.utc)
        task_record = CeleryTaskExecution(
            task_name=task_name,
            task_args_hash=args_hash,
            task_args=task_args,
            celery_task_id=celery_task_id,
            status="PENDING",
            started_at=now_utc
        )

        async with self.db_client() as session:
            async with session.begin():
                session.add(task_record)
            await session.refresh(task_record)
            return task_record

    async def update_task_status(
        self,
        execution_id: int,
        status: str,
        result: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update task status, timestamp, and optional result payload."""
        async with self.db_client() as session:
            async with session.begin():
                task_record = await session.get(CeleryTaskExecution, execution_id)
                if task_record:
                    task_record.status = status
                    if result is not None:
                        task_record.result = result
                    if status in ["SUCCESS", "FAILURE"]:
                        task_record.completed_at = datetime.now(timezone.utc)

    async def get_existing_task(
        self,
        task_name: str,
        task_args: Dict[str, Any],
        celery_task_id: Optional[str]
    ) -> Optional[CeleryTaskExecution]:
        """Check if task with same name and args already exists."""
        args_hash = self.create_args_hash(task_name, task_args)

        async with self.db_client() as session:
            stmt = select(CeleryTaskExecution).where(
                CeleryTaskExecution.celery_task_id == celery_task_id,
                CeleryTaskExecution.task_name == task_name,
                CeleryTaskExecution.task_args_hash == args_hash
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def should_execute_task(
        self,
        task_name: str,
        task_args: Dict[str, Any],
        celery_task_id: Optional[str],
        task_time_limit: int = 600
    ) -> Tuple[bool, Optional[CeleryTaskExecution]]:
        """
        Check if task should be executed or return existing result.
        
        Args:
            task_time_limit: Time limit in seconds after which a stuck task can be re-executed.
            
        Returns:
            Tuple of (should_execute: bool, existing_task: Optional[CeleryTaskExecution])
        """
        existing_task = await self.get_existing_task(task_name, task_args, celery_task_id)

        if not existing_task:
            return True, None

        # Don't re-execute if already completed successfully
        if existing_task.status == "SUCCESS":
            return False, existing_task

        # Check if task is stuck beyond time limit + grace period
        if existing_task.status in ["PENDING", "STARTED", "RETRY"]:
            if existing_task.started_at:
                started_at = existing_task.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)

                time_elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                grace_period = 60
                if time_elapsed > (task_time_limit + grace_period):
                    return True, existing_task  # Stuck task, permit re-execution

            return False, existing_task  # Still running within valid time limit

        # Re-execute if previous task failed
        return True, existing_task

    async def cleanup_old_tasks(
        self,
        days: int = 5,
        time_retention: Optional[int] = None
    ) -> int:
        """
        Delete old task records older than retention period.
        
        Args:
            days: Retention window in days (default: 5).
            time_retention: Optional override in seconds.
        """
        seconds = time_retention if time_retention is not None else (days * 86400)
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)

        async with self.db_client() as session:
            async with session.begin():
                stmt = delete(CeleryTaskExecution).where(
                    CeleryTaskExecution.created_at < cutoff_time
                )
                result = await session.execute(stmt)
                return result.rowcount