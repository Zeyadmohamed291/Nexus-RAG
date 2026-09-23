import logging
from typing import List, Optional, Dict, Any, Union
from qdrant_client import models, QdrantClient
from ..VectorDBInterface import VectorDBInterface
from ..VectorDBEnums import DistanceMethodEnums
from models.db_schemes import RetrievedDocument

logger = logging.getLogger(__name__)


class QdrantDBProvider(VectorDBInterface):
    """
    Qdrant Vector Database Provider.
    Supports in-memory, local embedded disk storage, and remote Qdrant servers.
    """

    _clients: Dict[str, QdrantClient] = {}

    def __init__(
        self,
        db_client: str,
        default_vector_size: int = 768,
        distance_method: Optional[str] = None,
        index_threshold: int = 100,
    ) -> None:
        self.client: Optional[QdrantClient] = None
        self.db_client: str = db_client
        self.default_vector_size: int = default_vector_size
        self.index_threshold: int = index_threshold

        self.distance_method = models.Distance.COSINE
        if distance_method == DistanceMethodEnums.COSINE.value:
            self.distance_method = models.Distance.COSINE
        elif distance_method == DistanceMethodEnums.DOT.value:
            self.distance_method = models.Distance.DOT

        self.logger = logger

    async def connect(self) -> None:
        """Initialize singleton connection to local or remote Qdrant store."""
        if self.db_client not in QdrantDBProvider._clients:
            QdrantDBProvider._clients[self.db_client] = QdrantClient(path=self.db_client)
        self.client = QdrantDBProvider._clients[self.db_client]

    async def disconnect(self) -> None:
        """Gracefully release client resources if applicable."""
        pass

    async def is_collection_existed(self, collection_name: str) -> bool:
        """Check whether the given collection exists."""
        if not self.client:
            return False
        return self.client.collection_exists(collection_name=collection_name)

    async def list_all_collections(self) -> List[Any]:
        """List all available collections in Qdrant."""
        if not self.client:
            return []
        return self.client.get_collections()

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """Fetch statistics and configuration of a collection."""
        if not await self.is_collection_existed(collection_name):
            return {"status": "not_found", "collection_name": collection_name}
        return self.client.get_collection(collection_name=collection_name)

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection by name."""
        if await self.is_collection_existed(collection_name):
            self.logger.info(f"Deleting collection: {collection_name}")
            return self.client.delete_collection(collection_name=collection_name)
        return False

    async def create_collection(
        self,
        collection_name: str,
        embedding_size: int,
        do_reset: bool = False
    ) -> bool:
        """Create vector collection with defined vector dimensions and distance metric."""
        if do_reset:
            await self.delete_collection(collection_name=collection_name)

        if not await self.is_collection_existed(collection_name):
            self.logger.info(f"Creating new Qdrant collection: {collection_name} (dim={embedding_size})")
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=embedding_size,
                    distance=self.distance_method or models.Distance.COSINE
                )
            )
            return True

        return False

    async def insert_one(
        self,
        collection_name: str,
        text: str,
        vector: list,
        metadata: Optional[dict] = None,
        record_id: Optional[Union[str, int]] = None
    ) -> bool:
        """Insert a single text record with vector embedding and payload metadata."""
        if not await self.is_collection_existed(collection_name):
            self.logger.error(f"Cannot insert record into non-existent collection: {collection_name}")
            return False

        try:
            self.client.upload_records(
                collection_name=collection_name,
                records=[
                    models.Record(
                        id=record_id,
                        vector=vector,
                        payload={"text": text, "metadata": metadata or {}}
                    )
                ]
            )
            return True
        except Exception as e:
            self.logger.error(f"Error while inserting record: {e}")
            return False

    async def insert_many(
        self,
        collection_name: str,
        texts: list,
        vectors: list,
        metadata: Optional[list] = None,
        record_ids: Optional[list] = None,
        batch_size: int = 50
    ) -> bool:
        """Batch-insert multiple documents with vectors and metadata into Qdrant."""
        if metadata is None:
            metadata = [None] * len(texts)

        if record_ids is None:
            record_ids = list(range(len(texts)))

        for i in range(0, len(texts), batch_size):
            batch_end = i + batch_size
            batch_texts = texts[i:batch_end]
            batch_vectors = vectors[i:batch_end]
            batch_metadata = metadata[i:batch_end]
            batch_record_ids = record_ids[i:batch_end]

            batch_records = [
                models.Record(
                    id=batch_record_ids[x],
                    vector=batch_vectors[x],
                    payload={
                        "text": batch_texts[x],
                        "metadata": batch_metadata[x] or {}
                    }
                )
                for x in range(len(batch_texts))
            ]

            try:
                self.client.upload_records(
                    collection_name=collection_name,
                    records=batch_records,
                )
            except Exception as e:
                self.logger.error(f"Error while inserting batch into Qdrant: {e}")
                return False

        return True

    async def search_by_vector(
        self,
        collection_name: str,
        vector: list,
        limit: int = 5
    ) -> Optional[List[RetrievedDocument]]:
        """Query Qdrant for top-K nearest neighbours by dense vector similarity."""
        try:
            if not await self.is_collection_existed(collection_name):
                return None

            results = self.client.search(
                collection_name=collection_name,
                query_vector=vector,
                limit=limit
            )

            if not results:
                return None

            return [
                RetrievedDocument(
                    score=result.score,
                    text=result.payload.get("text", "")
                )
                for result in results
            ]
        except Exception as e:
            self.logger.error(f"Error while searching in Qdrant: {e}")
            return None
