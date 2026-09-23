from pathlib import Path
from typing import Union
from .BaseController import BaseController


class ProjectController(BaseController):
    """
    Project controller managing file system storage isolation for distinct projects.
    """

    def __init__(self) -> None:
        super().__init__()

    def get_project_path(self, project_id: Union[int, str]) -> str:
        """
        Retrieve and ensure the dedicated asset directory exists for a given project.
        
        Args:
            project_id: Unique identifier for the project.
            
        Returns:
            Absolute directory path as a string.
        """
        project_dir = Path(self.files_dir) / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        return str(project_dir)
