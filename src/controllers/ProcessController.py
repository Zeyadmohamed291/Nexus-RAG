import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
import logging

from langchain_community.document_loaders import TextLoader, PyMuPDFLoader
from models import ProcessingEnum
from .BaseController import BaseController
from .ProjectController import ProjectController

logger = logging.getLogger(__name__)


@dataclass
class Document:
    page_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProcessController(BaseController):
    """
    Process controller managing file loading (TXT, PDF) and semantic/sliding-window chunking
    with true overlap support and metadata preservation.
    """

    def __init__(self, project_id: Union[int, str]) -> None:
        super().__init__()
        self.project_id: str = str(project_id)
        self.project_path: str = ProjectController().get_project_path(project_id=self.project_id)

    def get_file_extension(self, file_id: str) -> str:
        """Extract the lowercase file extension."""
        return Path(file_id).suffix.lower()

    def get_file_loader(self, file_id: str):
        """
        Resolve the appropriate LangChain document loader based on the file extension.
        """
        file_ext = self.get_file_extension(file_id=file_id)
        file_path = Path(self.project_path) / file_id

        if not file_path.exists():
            logger.warning(f"Target file does not exist: {file_path}")
            return None

        if file_ext == ProcessingEnum.TXT.value:
            return TextLoader(str(file_path), encoding="utf-8")

        if file_ext == ProcessingEnum.PDF.value:
            return PyMuPDFLoader(str(file_path))

        logger.error(f"Unsupported file extension: {file_ext}")
        return None

    def get_file_content(self, file_id: str) -> Optional[List[Any]]:
        """
        Load document pages from the specified file.
        """
        loader = self.get_file_loader(file_id=file_id)
        if loader:
            try:
                return loader.load()
            except Exception as e:
                logger.error(f"Error loading file {file_id}: {e}")
                return None
        return None

    def process_file_content(
        self,
        file_content: List[Any],
        file_id: str,
        chunk_size: int = 100,
        overlap_size: int = 20,
    ) -> List[Document]:
        """
        Process loaded pages into chunks with sliding-window overlap and metadata preservation.
        """
        if not file_content:
            return []

        chunks: List[Document] = []

        for doc_idx, doc in enumerate(file_content):
            page_text = getattr(doc, "page_content", "") or ""
            base_meta = getattr(doc, "metadata", {}) or {}
            base_meta.update({
                "file_id": file_id,
                "project_id": self.project_id,
                "doc_page": base_meta.get("page", doc_idx + 1),
            })

            page_chunks = self.process_simpler_splitter(
                texts=[page_text],
                metadatas=[base_meta],
                chunk_size=chunk_size,
                overlap_size=overlap_size,
            )
            chunks.extend(page_chunks)

        return chunks

    def process_simpler_splitter(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        chunk_size: int = 250,
        overlap_size: int = 40,
        splitter_tag: str = "\n",
    ) -> List[Document]:
        """
        Sliding-window text chunker respecting chunk_size and overlap_size,
        preserving line boundaries and avoiding empty chunk artifacts.
        """
        full_text = " ".join([t for t in texts if t]).strip()
        if not full_text:
            return []

        # Ensure valid chunk bounds
        chunk_size = max(50, chunk_size)
        overlap_size = min(max(0, overlap_size), chunk_size - 10)

        step_size = chunk_size - overlap_size
        shared_metadata = (metadatas[0] if metadatas and len(metadatas) > 0 else {}).copy()

        chunks: List[Document] = []
        start_idx = 0
        text_length = len(full_text)

        while start_idx < text_length:
            end_idx = min(start_idx + chunk_size, text_length)

            # Avoid cutting words in the middle when possible
            if end_idx < text_length:
                next_space = full_text.rfind(" ", start_idx + overlap_size, end_idx)
                if next_space != -1 and next_space > start_idx:
                    end_idx = next_space

            chunk_text = full_text[start_idx:end_idx].strip()
            if chunk_text:
                chunk_meta = shared_metadata.copy()
                chunk_meta["chunk_char_start"] = start_idx
                chunk_meta["chunk_char_end"] = end_idx
                chunks.append(Document(page_content=chunk_text, metadata=chunk_meta))

            if end_idx >= text_length:
                break

            start_idx += step_size

        return chunks
