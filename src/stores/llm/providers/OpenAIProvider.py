import logging
from typing import List, Union, Optional, Dict, Any
from openai import OpenAI
from ..LLMInterface import LLMInterface
from ..LLMEnums import OpenAIEnums

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMInterface):
    """
    OpenAI LLM & Embeddings Provider.
    Supports official OpenAI models as well as custom compatible base URLs (e.g., Ollama, vLLM).
    """

    def __init__(
        self,
        api_key: str,
        api_url: Optional[str] = None,
        default_input_max_characters: int = 1000,
        default_generation_max_output_tokens: int = 1000,
        default_generation_temperature: float = 0.1,
    ) -> None:
        self.api_key: str = api_key
        self.api_url: Optional[str] = api_url

        self.default_input_max_characters: int = default_input_max_characters
        self.default_generation_max_output_tokens: int = default_generation_max_output_tokens
        self.default_generation_temperature: float = default_generation_temperature

        self.generation_model_id: Optional[str] = None
        self.embedding_model_id: Optional[str] = None
        self.embedding_size: Optional[int] = None

        self.client: Optional[OpenAI] = None
        if self.api_key or self.api_url:
            self.client = OpenAI(
                api_key=self.api_key or "sk-no-key-required",
                base_url=self.api_url if self.api_url and len(self.api_url.strip()) else None,
            )

        self.enums = OpenAIEnums
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
        """Generate response text using OpenAI chat completions without mutating caller history."""
        if not self.client:
            self.logger.error("OpenAI client was not initialized")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for OpenAI was not set")
            return None

        tokens = max_output_tokens if max_output_tokens is not None else self.default_generation_max_output_tokens
        temp = temperature if temperature is not None else self.default_generation_temperature

        # Create isolated message list to avoid in-place mutation of caller history
        messages: List[Dict[str, Any]] = list(chat_history) if chat_history else []
        messages.append(
            self.construct_prompt(prompt=prompt, role=OpenAIEnums.USER.value)
        )

        try:
            response = self.client.chat.completions.create(
                model=self.generation_model_id,
                messages=messages,
                max_tokens=tokens,
                temperature=temp,
            )

            if not response or not response.choices or not response.choices[0].message:
                self.logger.error("Empty response received from OpenAI completions")
                return None

            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"Error while generating text with OpenAI: {e}")
            return None

    def embed_text(
        self,
        text: Union[str, List[str]],
        document_type: Optional[str] = None
    ) -> Optional[List[List[float]]]:
        """Generate vector embeddings for input strings."""
        if not self.client:
            self.logger.error("OpenAI client was not initialized")
            return None

        if isinstance(text, str):
            text = [text]

        if not self.embedding_model_id:
            self.logger.error("Embedding model for OpenAI was not set")
            return None

        try:
            processed_texts = [self.process_text(t) for t in text]
            embed_kwargs: Dict[str, Any] = {
                "model": self.embedding_model_id,
                "input": processed_texts,
            }
            if self.embedding_size:
                embed_kwargs["dimensions"] = self.embedding_size

            response = self.client.embeddings.create(**embed_kwargs)

            if not response or not response.data:
                self.logger.error("Empty response received from OpenAI embeddings")
                return None

            return [rec.embedding for rec in response.data]
        except Exception as e:
            self.logger.error(f"Error while embedding text with OpenAI: {e}")
            return None

    def construct_prompt(self, prompt: str, role: str) -> Dict[str, str]:
        """Construct standard OpenAI chat message dict."""
        return {
            "role": role,
            "content": prompt,
        }
