from typing import List, Optional, Union
from sqlalchemy.future import select
from sqlalchemy import func, delete
from .BaseDataModel import BaseDataModel
from .db_schemes import DataChunk


class ChunkModel(BaseDataModel):
    """
    Data access layer for document text chunks stored in PostgreSQL.
    """

    def __init__(self, db_client: object) -> None:
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object) -> "ChunkModel":
        return cls(db_client)

    async def create_chunk(self, chunk: DataChunk) -> DataChunk:
        """Persist a single chunk to the database."""
        async with self.db_client() as session:
            async with session.begin():
                session.add(chunk)
            await session.refresh(chunk)
        return chunk

    async def get_chunk(self, chunk_id: Union[int, str]) -> Optional[DataChunk]:
        """Fetch a specific chunk by its primary key ID."""
        async with self.db_client() as session:
            result = await session.execute(
                select(DataChunk).where(DataChunk.chunk_id == chunk_id)
            )
            return result.scalar_one_or_none()

    async def insert_many_chunks(self, chunks: List[DataChunk], batch_size: int = 100) -> int:
        """Batch-insert chunk records efficiently."""
        if not chunks:
            return 0

        async with self.db_client() as session:
            async with session.begin():
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i:i + batch_size]
                    session.add_all(batch)
        return len(chunks)

    async def delete_chunks_by_project_id(self, project_id: Union[int, str]) -> int:
        """Delete all chunk records belonging to a project."""
        async with self.db_client() as session:
            async with session.begin():
                stmt = delete(DataChunk).where(DataChunk.chunk_project_id == project_id)
                result = await session.execute(stmt)
                return result.rowcount

    async def get_project_chunks(
        self,
        project_id: Union[int, str],
        page_no: int = 1,
        page_size: int = 50
    ) -> List[DataChunk]:
        """Paginated retrieval of chunk records for a given project."""
        offset = max(0, (page_no - 1) * page_size)
        async with self.db_client() as session:
            stmt = (
                select(DataChunk)
                .where(DataChunk.chunk_project_id == project_id)
                .offset(offset)
                .limit(page_size)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # Backward-compatible alias for existing codebase calls
    get_poject_chunks = get_project_chunks

    async def get_total_chunks_count(self, project_id: Union[int, str]) -> int:
        """Count total stored chunks for a given project."""
        async with self.db_client() as session:
            count_sql = (
                select(func.count(DataChunk.chunk_id))
                .where(DataChunk.chunk_project_id == project_id)
            )
            records_count = await session.execute(count_sql)
            return records_count.scalar() or 0
