import asyncio
from typing import List, Optional
from core.config import settings
from core.logger import info, timer_step
from sentence_transformers import SentenceTransformer

# Global model instance for lazy loading to prevent multiple memory allocations
_model_instance = None

class EmbeddingClient:
    """
    Client for generating text embeddings using local sentence-transformers models.
    Executes inference in a background thread to prevent blocking the async event loop.
    """
    
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.dimension = settings.EMBEDDING_DIMENSION

    def _get_model(self) -> SentenceTransformer:
        """Lazily load the sentence transformer model into memory."""
        global _model_instance
        if _model_instance is None:
            info("embeddings", f"Loading local embedding model: {self.model_name} into memory...")
            _model_instance = SentenceTransformer(self.model_name)
        return _model_instance

    def _embed_sync(self, texts: List[str]) -> List[List[float]]:
        """Synchronous embedding inference."""
        model = self._get_model()
        # sentence-transformers returns a numpy array, we convert to standard float lists
        embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return embeddings.tolist()

    async def get_embedding(self, text: str) -> List[float]:
        """Generate an embedding vector for a single text chunk (non-blocking)."""
        with timer_step("embeddings", f"Local embedding inference (single)"):
            embeddings = await asyncio.to_thread(self._embed_sync, [text])
            return embeddings[0]

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a batch of text chunks (non-blocking)."""
        if not texts:
            return []
        with timer_step("embeddings", f"Local embedding inference (batch size: {len(texts)})"):
            embeddings = await asyncio.to_thread(self._embed_sync, texts)
            return embeddings
