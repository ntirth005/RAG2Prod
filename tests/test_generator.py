"""
Tests for the Generation Layer (Stage 5).
Tests LLMClient mock fallback and RAGPipeline orchestration.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.schemas import (
    QueryRequest,
    GenerationResult,
    TokenUsage,
    PromptPayload,
    FormattedContext,
    CitationSource,
    RetrievalResult,
    RetrievalResultItem,
)
from core.generator import LLMClient, RAGPipeline


# ── LLMClient Tests ──

def test_llm_client_invalid_provider() -> None:
    """Should raise ValueError for unsupported providers."""
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMClient(provider="nonexistent")


def test_llm_client_valid_providers() -> None:
    """Should accept 'deepseek' and 'openai' providers."""
    deepseek = LLMClient(provider="deepseek")
    assert deepseek.provider == "deepseek"

    openai = LLMClient(provider="openai")
    assert openai.provider == "openai"


async def test_mock_generation_no_api_key() -> None:
    """Without an API key, LLMClient should return a mock response."""
    client = LLMClient(provider="deepseek", api_key="")

    prompt = PromptPayload(
        system_message="You are a helpful assistant.",
        user_message="Test question based on context.",
        context_tokens=100,
    )

    answer, usage = await client.generate(prompt)

    assert "[Mock Response" in answer
    assert "Test question" in answer
    assert isinstance(usage, TokenUsage)


async def test_mock_streaming_no_api_key() -> None:
    """Without an API key, stream() should yield mock tokens word-by-word."""
    client = LLMClient(provider="deepseek", api_key="")

    prompt = PromptPayload(
        system_message="You are a helpful assistant.",
        user_message="Test query context.",
        context_tokens=50,
    )

    tokens = []
    async for token in client.stream(prompt):
        tokens.append(token)

    full_text = "".join(tokens)
    assert "[Mock Response" in full_text
    assert len(tokens) > 1  # Should yield multiple chunks


def test_build_request_body() -> None:
    """Request body should follow OpenAI-compatible format."""
    client = LLMClient(provider="deepseek", api_key="test-key")
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Hello"},
    ]
    body = client._build_request_body(messages, stream=True)

    assert body["model"] == client.model_name
    assert body["messages"] == messages
    assert body["stream"] is True
    assert "temperature" in body
    assert "max_tokens" in body


def test_build_headers() -> None:
    """Headers should include Bearer auth."""
    client = LLMClient(provider="openai", api_key="sk-test-key")
    headers = client._build_headers()

    assert headers["Authorization"] == "Bearer sk-test-key"
    assert headers["Content-Type"] == "application/json"


# ── RAGPipeline Tests ──

def _make_mock_retrieval_result() -> RetrievalResult:
    """Create a mock retrieval result for pipeline tests."""
    return RetrievalResult(
        query_text="What are the placement statistics?",
        total_retrieved=2,
        items=[
            RetrievalResultItem(
                chunk_id="chunk_a",
                parent_id="parent_a",
                document_id="doc_placement",
                chunk_text="The placement rate was 95% in 2025.",
                parent_text="University placement brochure: The placement rate was 95% in 2025 with 200+ companies visiting campus.",
                similarity_score=0.92,
                source_metadata={"page_number": 3},
            ),
            RetrievalResultItem(
                chunk_id="chunk_b",
                parent_id="parent_b",
                document_id="doc_placement",
                chunk_text="Average package was 12 LPA.",
                parent_text="Salary statistics: Average package was 12 LPA, with the highest reaching 45 LPA.",
                similarity_score=0.87,
                source_metadata={"page_number": 5},
            ),
        ],
    )


@patch("core.generator.DenseRetriever")
async def test_rag_pipeline_end_to_end(MockRetriever) -> None:
    """Full pipeline should chain retrieval → context → generation with mock LLM."""
    # Mock the retriever
    mock_retriever_instance = AsyncMock()
    mock_retriever_instance.search.return_value = _make_mock_retrieval_result()
    mock_retriever_instance.search_multi.return_value = _make_mock_retrieval_result()
    MockRetriever.return_value = mock_retriever_instance

    mock_session = AsyncMock()
    pipeline = RAGPipeline(session=mock_session, provider="deepseek")
    pipeline.retriever = mock_retriever_instance

    request = QueryRequest(
        query_text="What are the placement statistics?",
        top_k=5,
        provider="deepseek",
    )

    result = await pipeline.run(request)

    assert isinstance(result, GenerationResult)
    assert len(result.answer) > 0
    assert len(result.citations) == 2
    assert result.citations[0].index == 1
    assert result.citations[1].index == 2
    assert result.retrieval_count == 2
    assert result.latency_ms > 0
    assert "deepseek" in result.model_used
    assert result.query_trace is not None
    assert result.query_trace.intent_class == "STATISTICAL"


@patch("core.generator.DenseRetriever")
async def test_rag_pipeline_no_results(MockRetriever) -> None:
    """Pipeline should return insufficient context message when no chunks found."""
    mock_retriever_instance = AsyncMock()
    empty_result = RetrievalResult(query_text="unknown query", total_retrieved=0, items=[])
    mock_retriever_instance.search.return_value = empty_result
    mock_retriever_instance.search_multi.return_value = empty_result
    MockRetriever.return_value = mock_retriever_instance

    mock_session = AsyncMock()
    pipeline = RAGPipeline(session=mock_session, provider="deepseek")
    pipeline.retriever = mock_retriever_instance

    request = QueryRequest(query_text="unknown query", top_k=5)
    result = await pipeline.run(request)

    assert "do not contain sufficient information" in result.answer
    assert len(result.citations) == 0
    assert result.retrieval_count == 0
    assert result.query_trace is not None


@patch("core.generator.DenseRetriever")
async def test_rag_pipeline_stream(MockRetriever) -> None:
    """Streaming pipeline should return an async generator, context, model_id, and query_trace."""
    mock_retriever_instance = AsyncMock()
    mock_retriever_instance.search.return_value = _make_mock_retrieval_result()
    mock_retriever_instance.search_multi.return_value = _make_mock_retrieval_result()
    MockRetriever.return_value = mock_retriever_instance

    mock_session = AsyncMock()
    pipeline = RAGPipeline(session=mock_session, provider="deepseek")
    pipeline.retriever = mock_retriever_instance

    request = QueryRequest(
        query_text="What are the placement statistics?",
        top_k=5,
        stream=True,
        provider="deepseek",
    )

    token_stream, context, model_id, query_trace = await pipeline.run_stream(request)

    assert "deepseek" in model_id
    assert len(context.citations) == 2
    assert query_trace.intent_class == "STATISTICAL"

    # Consume the stream
    tokens = []
    async for token in token_stream:
        tokens.append(token)

    full_text = "".join(tokens)
    assert len(full_text) > 0
