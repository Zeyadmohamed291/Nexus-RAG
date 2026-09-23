import json
import logging
from typing import List, Optional, Tuple, Dict, Any
from .BaseController import BaseController
from models.db_schemes import Project, DataChunk, RetrievedDocument
from stores.llm.LLMEnums import DocumentTypeEnum

logger = logging.getLogger(__name__)


class NLPController(BaseController):
    """
    NLP Controller orchestrating embedding generation, vector database indexing,
    semantic search, and context-augmented answer generation.
    """

    def __init__(
        self,
        vectordb_client,
        generation_client,
        embedding_client,
        template_parser
    ) -> None:
        super().__init__()
        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        self.template_parser = template_parser

    def create_collection_name(self, project_id: Any) -> str:
        """Standardized naming convention for vector database collections."""
        return f"collection_{self.vectordb_client.default_vector_size}_{str(project_id)}".strip()

    async def reset_vector_db_collection(self, project: Project) -> bool:
        """Delete and reset the project's vector database collection."""
        collection_name = self.create_collection_name(project_id=project.project_id)
        return await self.vectordb_client.delete_collection(collection_name=collection_name)

    async def get_vector_db_collection_info(self, project: Project) -> Dict[str, Any]:
        """Fetch metadata and statistics of the project's vector collection."""
        collection_name = self.create_collection_name(project_id=project.project_id)
        collection_info = await self.vectordb_client.get_collection_info(collection_name=collection_name)

        return json.loads(
            json.dumps(collection_info, default=lambda x: getattr(x, "__dict__", str(x)))
        )

    async def index_into_vector_db(
        self,
        project: Project,
        chunks: List[DataChunk],
        chunks_ids: List[int],
        do_reset: bool = False
    ) -> bool:
        """
        Embed document chunks and batch-insert them into the vector database.
        """
        if not chunks:
            return True

        collection_name = self.create_collection_name(project_id=project.project_id)
        texts = [c.chunk_text for c in chunks]
        metadata = [c.chunk_metadata or {} for c in chunks]

        # Generate dense embeddings
        vectors = self.embedding_client.embed_text(
            text=texts,
            document_type=DocumentTypeEnum.DOCUMENT.value
        )

        if not vectors:
            logger.error("Failed to generate embeddings for chunks batch.")
            return False

        # Ensure collection exists
        await self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.embedding_client.embedding_size,
            do_reset=do_reset,
        )

        # Batch insert into vector store
        return await self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=texts,
            metadata=metadata,
            vectors=vectors,
            record_ids=chunks_ids,
        )

    async def search_vector_db_collection(
        self,
        project: Project,
        text: str,
        limit: int = 10
    ) -> Optional[List[RetrievedDocument]]:
        """
        Perform semantic similarity search over indexed chunks for the given query.
        """
        collection_name = self.create_collection_name(project_id=project.project_id)

        vectors = self.embedding_client.embed_text(
            text=text,
            document_type=DocumentTypeEnum.QUERY.value
        )

        if not vectors:
            logger.warning("Empty or failed embedding for search query.")
            return None

        # Normalize single vector embedding format
        if isinstance(vectors[0], (int, float)):
            query_vector = vectors
        elif isinstance(vectors, list) and len(vectors) > 0:
            query_vector = vectors[0]
        else:
            return None

        results = await self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            vector=query_vector,
            limit=limit
        )

        return results if results else None

    async def answer_rag_question(
        self,
        project: Project,
        query: str,
        limit: int = 10
    ) -> Tuple[Optional[str], Optional[str], Optional[List[Dict[str, Any]]]]:
        """
        Execute full RAG cycle:
        1. Retrieve semantically relevant context chunks.
        2. Format augmented prompt using localized templates.
        3. Invoke generation LLM backend.
        """
        retrieved_documents = await self.search_vector_db_collection(
            project=project,
            text=query,
            limit=limit,
        )

        if not retrieved_documents:
            logger.info(f"No relevant documents found in vector DB for query in project {project.project_id}")
            return None, None, None

        # Render system and document context prompts
        system_prompt = self.template_parser.get("rag", "system_prompt")

        documents_prompts = "\n".join([
            self.template_parser.get(
                "rag",
                "document_prompt",
                {
                    "doc_num": idx + 1,
                    "chunk_text": self.generation_client.process_text(doc.text),
                }
            )
            for idx, doc in enumerate(retrieved_documents)
        ])

        footer_prompt = self.template_parser.get("rag", "footer_prompt", {"query": query})

        chat_history = [
            self.generation_client.construct_prompt(
                prompt=system_prompt,
                role=self.generation_client.enums.SYSTEM.value,
            )
        ]

        full_prompt = f"{documents_prompts}\n\n{footer_prompt}"

        answer = self.generation_client.generate_text(
            prompt=full_prompt,
            chat_history=chat_history
        )

        return answer, full_prompt, chat_history
