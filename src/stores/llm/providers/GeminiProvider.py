import logging
from typing import List, Union, Optional, Dict, Any
import google.generativeai as genai
from ..LLMInterface import LLMInterface
from ..LLMEnums import GeminiEnums, DocumentTypeEnum

logger = logging.getLogger(__name__)


class GeminiProvider(LLMInterface):
    """
    Google Gemini LLM & Embeddings Provider.
    Supports chat completion and dense vector embeddings with task-specific optimization.
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

        if self.api_key:
            genai.configure(api_key=self.api_key)

        self.enums = GeminiEnums
        self.logger = logger

    def set_generation_model(self, model_id: str) -> None:
        """Assign target generation model identifier."""
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int) -> None:
        """Assign target embedding model identifier and dimensions."""
        if model_id and not model_id.startswith("models/"):
            model_id = f"models/{model_id}"
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
        """Generate response text using Google Generative AI."""
        if not self.generation_model_id:
            self.logger.error("Generation model for Gemini was not set")
            return None

        tokens = max_output_tokens if max_output_tokens is not None else self.default_generation_max_output_tokens
        temp = temperature if temperature is not None else self.default_generation_temperature

        generation_config = genai.types.GenerationConfig(
            max_output_tokens=tokens,
            temperature=temp,
        )

        history = chat_history or []
        system_instruction = None
        filtered_history: List[Dict[str, Any]] = []

        for msg in history:
            if msg.get("role") == self.enums.SYSTEM.value:
                parts = msg.get("parts")
                system_instruction = parts[0] if parts else None
            else:
                filtered_history.append(msg)

        try:
            model = genai.GenerativeModel(
                model_name=self.generation_model_id,
                system_instruction=system_instruction
            )

            if filtered_history:
                chat = model.start_chat(history=filtered_history)
                response = chat.send_message(prompt, generation_config=generation_config)
            else:
                response = model.generate_content(prompt, generation_config=generation_config)

            return response.text
        except Exception as e:
            self.logger.error(f"Error while generating text with Gemini: {e}")
            return None

    def embed_text(
        self,
        text: Union[str, List[str]],
        document_type: Optional[str] = None
    ) -> Optional[List[Any]]:
        """Compute embeddings using Google Generative AI."""
        if isinstance(text, str):
            text = [text]

        if not self.embedding_model_id:
            self.logger.error("Embedding model for Gemini was not set")
            return None

        task_type = self.enums.DOCUMENT.value
        if document_type == DocumentTypeEnum.QUERY.value:
            task_type = self.enums.QUERY.value

        try:
            processed_texts = [self.process_text(t) for t in text]
            embed_kwargs = {
                "model": self.embedding_model_id,
                "content": processed_texts,
                "task_type": task_type,
            }
            if self.embedding_size:
                embed_kwargs["output_dimensionality"] = self.embedding_size

            response = genai.embed_content(**embed_kwargs)
            embeddings = response.get("embedding", [])
            if not embeddings:
                self.logger.error("Empty embedding response returned by Gemini")
                return None

            return embeddings
        except Exception as e:
            self.logger.error(f"Error while embedding text with Gemini: {e}")
            return None

    def construct_prompt(self, prompt: str, role: str) -> Dict[str, Any]:
        """Construct standard Gemini chat message dict."""
        return {
            "role": role,
            "parts": [prompt],
        }
