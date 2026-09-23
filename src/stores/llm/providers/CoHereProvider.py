import logging
from typing import List, Union, Optional, Dict, Any
import cohere
from ..LLMInterface import LLMInterface
from ..LLMEnums import CoHereEnums, DocumentTypeEnum

logger = logging.getLogger(__name__)


class CoHereProvider(LLMInterface):
    """
    Cohere LLM & Embeddings Provider.
    Supports Command models for generation and Embed-v3 with input_type specification.
    """

    def __init__(
        self,
        api_key: str,
        default_input_max_characters: int = 1000,
        default_generation_max_output_tokens: int = 1000,
        default_generation_temperature: float = 0.1,
    ) -> None:
        self.api_key: str = api_key
        self.default_input_max_characters: int = default_input_max_characters
        self.default_generation_max_output_tokens: int = default_generation_max_output_tokens
        self.default_generation_temperature: float = default_generation_temperature

        self.generation_model_id: Optional[str] = None
        self.embedding_model_id: Optional[str] = None
        self.embedding_size: Optional[int] = None

        self.client: Optional[cohere.Client] = None
        if self.api_key:
            self.client = cohere.Client(api_key=self.api_key)

        self.enums = CoHereEnums
        self.logger = logger

    def set_generation_model(self, model_id: str) -> None:
        """Assign target generation model identifier."""
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int) -> None:
        """Assign target embedding model identifier and dimensions."""
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def process_text(self, text: str) -> str:
        """Truncate input string according to default character limits."""
        return (text or "")[:self.default_input_max_characters].strip()

    def generate_text(
        self,
        prompt: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        max_output_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Optional[str]:
        """Generate response text using Cohere chat API."""
        if not self.client:
            self.logger.error("Cohere client was not initialized")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for Cohere was not set")
            return None

        tokens = max_output_tokens if max_output_tokens is not None else self.default_generation_max_output_tokens
        temp = temperature if temperature is not None else self.default_generation_temperature

        try:
            response = self.client.chat(
                model=self.generation_model_id,
                chat_history=chat_history or [],
                message=self.process_text(prompt),
                temperature=temp,
                max_tokens=tokens,
            )

            if not response or not response.text:
                self.logger.error("Empty text response received from Cohere")
                return None

            return response.text
        except Exception as e:
            self.logger.error(f"Error while generating text with Cohere: {e}")
            return None

    def embed_text(
        self,
        text: Union[str, List[str]],
        document_type: Optional[str] = None
    ) -> Optional[List[List[float]]]:
        """Generate vector embeddings for input strings using Cohere embed API."""
        if not self.client:
            self.logger.error("Cohere client was not initialized")
            return None

        if isinstance(text, str):
            text = [text]

        if not self.embedding_model_id:
            self.logger.error("Embedding model for Cohere was not set")
            return None

        # Resolve proper input_type string (search_query or search_document)
        is_query = (
            document_type == DocumentTypeEnum.QUERY.value
            or document_type == DocumentTypeEnum.QUERY
            or document_type == "query"
        )
        input_type = CoHereEnums.QUERY.value if is_query else CoHereEnums.DOCUMENT.value

        try:
            processed_texts = [self.process_text(t) for t in text]
            response = self.client.embed(
                model=self.embedding_model_id,
                texts=processed_texts,
                input_type=input_type,
                embedding_types=["float"],
            )

            if not response or not response.embeddings or not response.embeddings.float:
                self.logger.error("Empty embedding returned by Cohere")
                return None

            return list(response.embeddings.float)
        except Exception as e:
            self.logger.error(f"Error while embedding text with Cohere: {e}")
            return None

    def construct_prompt(self, prompt: str, role: str) -> Dict[str, str]:
        """Construct standard Cohere chat message dict."""
        return {
            "role": role,
            "text": prompt,
        }