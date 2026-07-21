import httpx
from typing import List, Optional
from core.config import settings
from core.logger import info
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class EmbeddingClient:
    """
    Client for generating text embeddings using the Gemini text-embedding-004 model.
    Includes a mock fallback for local testing and dev environments when API keys are missing.
    """
    
    _http_client = None

    @classmethod
    def get_http_client(cls) -> httpx.AsyncClient:
        if cls._http_client is None:
            cls._http_client = httpx.AsyncClient(limits=httpx.Limits(max_connections=100, max_keepalive_connections=20))
        return cls._http_client

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.dimension = settings.EMBEDDING_DIMENSION

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True
    )
    async def get_embedding(self, text: str) -> List[float]:
        """Generate an embedding vector for a single text chunk."""
        if not self.api_key:
            # Fallback mock for testing (generates a deterministic float list of embedding size)
            info("embeddings", "No API key — using mock embedding")
            return self._generate_mock_embedding(text)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:embedContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": f"models/{self.model_name}",
            "content": {
                "parts": [{"text": text}]
            }
        }

        client = self.get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=20.0)
        response.raise_for_status()
        resp_data = response.json()
        return resp_data["embedding"]["values"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True
    )
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a batch of text chunks."""
        # Using Gemini batch endpoint: batchEmbedContents
        if not self.api_key:
            info("embeddings", f"No API key — using mock for {len(texts)} texts")
            return [self._generate_mock_embedding(text) for text in texts]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:batchEmbedContents?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        requests = [
            {
                "model": f"models/{self.model_name}",
                "content": {"parts": [{"text": text}]}
            } for text in texts
        ]
        payload = {"requests": requests}

        client = self.get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        resp_data = response.json()
        return [emb["values"] for emb in resp_data["embeddings"]]

    def _generate_mock_embedding(self, text: str) -> List[float]:
        """Generate a deterministic mock embedding vector of the configured dimension size."""
        import hashlib
        # Use MD5 of text to get deterministic floats
        hashed = hashlib.md5(text.encode("utf-8")).hexdigest()
        raw_vals = [int(hashed[i:i+2], 16) / 255.0 for i in range(0, 32, 2)]
        
        # Tile values to match the required dimension size (e.g. 384)
        embedding = []
        while len(embedding) < self.dimension:
            embedding.extend(raw_vals)
        return embedding[:self.dimension]
