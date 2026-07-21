import pytest
from unittest.mock import AsyncMock, MagicMock
from core.schemas import RetrievalQuery, RetrievalResultItem
from core.retriever import SparseRetriever, CrossEncoderReranker, HybridRetriever

@pytest.mark.asyncio
async def test_sparse_bm25_retriever() -> None:
    # Mock SQLAlchemy Session
    mock_session = AsyncMock()
    
    mock_child1 = MagicMock(id="c1", parent_id="p1", document_id="doc1", source_metadata={})
    mock_child1.text = "Python function def connect_db(uri: str) to PostgreSQL"
    mock_parent1 = MagicMock(id="p1", text="Full parent 1")

    mock_child2 = MagicMock(id="c2", parent_id="p2", document_id="doc1", source_metadata={})
    mock_child2.text = "User authentication token validation module"
    mock_parent2 = MagicMock(id="p2", text="Full parent 2")

    mock_child3 = MagicMock(id="c3", parent_id="p3", document_id="doc1", source_metadata={})
    mock_child3.text = "Frontend React dashboard layout and UI components"
    mock_parent3 = MagicMock(id="p3", text="Full parent 3")

    mock_result = MagicMock()
    mock_result.all.return_value = [
        (mock_child1, mock_parent1),
        (mock_child2, mock_parent2),
        (mock_child3, mock_parent3),
    ]
    mock_session.execute.return_value = mock_result

    sparse_retriever = SparseRetriever(mock_session)
    query = RetrievalQuery(query_text="connect_db PostgreSQL", top_k=5, mode="sparse")
    
    res = await sparse_retriever.search(query)
    assert res.total_retrieved >= 1
    assert res.items[0].chunk_id == "c1"
    assert "connect_db" in res.items[0].chunk_text

def test_cross_encoder_reranker_fallback() -> None:
    reranker = CrossEncoderReranker()
    item1 = RetrievalResultItem(
        chunk_id="c1", parent_id="p1", document_id="doc1",
        chunk_text="Database connection connect_db timeout config", parent_text="", similarity_score=0.7
    )
    item2 = RetrievalResultItem(
        chunk_id="c2", parent_id="p2", document_id="doc1",
        chunk_text="Generic user interface CSS styling guidelines", parent_text="", similarity_score=0.85
    )

    reranked = reranker.rerank("connect_db timeout", [item1, item2], top_k=2)
    assert len(reranked) == 2
    # item1 has direct lexical overlap with query terms 'connect_db' and 'timeout'
    assert reranked[0].chunk_id == "c1"

@pytest.mark.asyncio
async def test_hybrid_retriever_rrf_fusion() -> None:
    mock_session = AsyncMock()
    mock_dense = AsyncMock()
    mock_sparse = AsyncMock()

    item_dense = RetrievalResultItem(
        chunk_id="c_dense", parent_id="p1", document_id="doc1",
        chunk_text="Dense semantic vector match for user login flow", parent_text="", similarity_score=0.9
    )
    item_sparse = RetrievalResultItem(
        chunk_id="c_sparse", parent_id="p2", document_id="doc1",
        chunk_text="Exact code keyword match for login_user()", parent_text="", similarity_score=0.8
    )

    mock_dense.search.return_value = MagicMock(items=[item_dense])
    mock_sparse.search.return_value = MagicMock(items=[item_sparse])

    hybrid = HybridRetriever(mock_session, dense_retriever=mock_dense, sparse_retriever=mock_sparse)
    query = RetrievalQuery(query_text="login_user", top_k=2, mode="hybrid", rerank=False)

    res = await hybrid.search(query)
    assert res.total_retrieved == 2
    chunk_ids = [item.chunk_id for item in res.items]
    assert "c_dense" in chunk_ids
    assert "c_sparse" in chunk_ids
