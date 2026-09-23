import os
import re
from pathlib import Path
from typing import Tuple, Union
from fastapi import UploadFile
from models import ResponseSignal
from .BaseController import BaseController
from .ProjectController import ProjectController


class DataController(BaseController):
    """
    Data controller managing uploaded document validation, unique storage resolution,
    and filename sanitization.
    """

    BYTES_PER_MB: int = 1024 * 1024

    def __init__(self) -> None:
        super().__init__()

    def validate_uploaded_file(self, file: UploadFile) -> Tuple[bool, str]:
        """
        Validate an uploaded file against allowed MIME types and maximum file size.
        
        Args:
            file: FastAPI UploadFile object.
            
        Returns:
            Tuple of (is_valid: bool, signal: str)
        """
        # Validate MIME type or file extension fallback
        allowed_types = self.app_settings.FILE_ALLOWED_TYPES
        file_ext = Path(file.filename or "").suffix.lower()
        allowed_extensions = {".txt", ".pdf"}

        is_valid_type = (file.content_type in allowed_types) or (file_ext in allowed_extensions)
        if not is_valid_type:
            return False, ResponseSignal.FILE_TYPE_NOT_SUPPORTED.value

        # Validate file size if available from headers
        max_bytes = self.app_settings.FILE_MAX_SIZE * self.BYTES_PER_MB
        if file.size is not None and file.size > max_bytes:
            return False, ResponseSignal.FILE_SIZE_EXCEEDED.value

        return True, ResponseSignal.FILE_VALIDATED_SUCCESS.value

    def generate_unique_filepath(self, orig_file_name: str, project_id: Union[int, str]) -> Tuple[str, str]:
        """
        Generate a collision-resistant unique file path within the project directory.
        
        Args:
            orig_file_name: Original name of the uploaded file.
            project_id: Project identifier.
            
        Returns:
            Tuple of (absolute_file_path: str, unique_file_id: str)
        """
        project_path = Path(ProjectController().get_project_path(project_id=project_id))
        cleaned_file_name = self.get_clean_file_name(orig_file_name=orig_file_name)

        while True:
            random_key = self.generate_random_string(length=12)
            file_id = f"{random_key}_{cleaned_file_name}"
            new_file_path = project_path / file_id
            if not new_file_path.exists():
                return str(new_file_path), file_id

    def get_clean_file_name(self, orig_file_name: str) -> str:
        """
        Sanitize filename removing unsafe special characters and path traversal patterns.
        
        Args:
            orig_file_name: Raw file name string.
            
        Returns:
            Sanitized safe file name.
        """
        # Strip directory components to avoid path traversal
        base_name = os.path.basename(orig_file_name.strip())
        
        # Replace spaces with underscores
        base_name = base_name.replace(" ", "_")

        # Allow only alphanumeric, underscore, dot, and hyphen
        cleaned_file_name = re.sub(r"[^\w.\-]", "", base_name)

        # Fallback if name becomes empty
        if not cleaned_file_name or cleaned_file_name.startswith("."):
            cleaned_file_name = f"document_{cleaned_file_name}"

        return cleaned_file_name
