import pytest
from core.embeddings import EmbeddingClient

@pytest.mark.asyncio
async def test_embedding_dimensions() -> None:
    client = EmbeddingClient(api_key=None) # force mock mode
    text = "Sample chunk text for embedding."
    
    vec = await client.get_embedding(text)
    assert len(vec) == 384
    assert all(isinstance(val, float) for val in vec)

@pytest.mark.asyncio
async def test_batch_embeddings() -> None:
    client = EmbeddingClient(api_key=None) # force mock mode
    texts = [
        "First chunk text.",
        "Second chunk text.",
        "Third chunk text."
    ]
    
    vecs = await client.get_embeddings(texts)
    assert len(vecs) == 3
    for vec in vecs:
        assert len(vec) == 384
        assert all(isinstance(val, float) for val in vec)

def test_deterministic_mock_embedding() -> None:
    client = EmbeddingClient(api_key=None)
    t1 = "Deterministic content test"
    t2 = "Deterministic content test"
    t3 = "Different content test"
    
    v1 = client._generate_mock_embedding(t1)
    v2 = client._generate_mock_embedding(t2)
    v3 = client._generate_mock_embedding(t3)
    
    assert v1 == v2
    assert v1 != v3
