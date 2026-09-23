from typing import List, Optional, Tuple, Union
from sqlalchemy.future import select
from sqlalchemy import func
from .BaseDataModel import BaseDataModel
from .db_schemes import Project


class ProjectModel(BaseDataModel):
    """
    Data access layer for projects/workspaces in NexusRAG.
    """

    def __init__(self, db_client: object) -> None:
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object) -> "ProjectModel":
        return cls(db_client)

    async def create_project(self, project: Project) -> Project:
        """Create and persist a new project record."""
        async with self.db_client() as session:
            async with session.begin():
                session.add(project)
            await session.refresh(project)
        return project

    async def get_project_or_create_one(self, project_id: Union[int, str]) -> Project:
        """Fetch project by ID or atomically create a new one if not found."""
        async with self.db_client() as session:
            async with session.begin():
                query = select(Project).where(Project.project_id == project_id)
                result = await session.execute(query)
                project = result.scalar_one_or_none()

                if project is None:
                    project = Project(project_id=project_id)
                    session.add(project)
                    # Exiting session.begin() will commit project

            await session.refresh(project)
            return project

    async def get_all_projects(self, page: int = 1, page_size: int = 10) -> Tuple[List[Project], int]:
        """Paginated retrieval of all registered projects."""
        offset = max(0, (page - 1) * page_size)
        async with self.db_client() as session:
            count_query = select(func.count(Project.project_id))
            total_documents = (await session.execute(count_query)).scalar() or 0

            total_pages = (total_documents + page_size - 1) // page_size if total_documents > 0 else 1

            query = select(Project).offset(offset).limit(page_size)
            projects = (await session.execute(query)).scalars().all()

            return list(projects), total_pages
