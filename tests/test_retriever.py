import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.database import init_db, async_session_maker
from core.storage_service import StorageService
from core.retriever import DenseRetriever
from core.schemas import RetrievalQuery, MetadataFilter


@pytest.mark.asyncio
async def test_dense_retriever_search_and_filtering() -> None:
    """
    Integration test verifying DenseRetriever similarity search and JSONB metadata filtering.
    Skips if live PostgreSQL database is unreachable.
    """
    initialized = await init_db()
    if not initialized:
        pytest.skip("PostgreSQL database is unreachable. Skipping DenseRetriever integration test.")

    with TemporaryDirectory() as temp_dir:
        doc_file = Path(temp_dir) / "retrieval_doc.txt"
        doc_file.write_text(
            "Dense vector search relies on approximate nearest neighbor HNSW indexes. "
            "Cosine distance is calculated using vector operators in Pgvector.",
            encoding="utf-8",
        )

        async with async_session_maker() as session:
            service = StorageService(session=session)
            ingest_res = await service.ingest_file(
                file_path=doc_file,
                doc_id="doc_retriever_test",
                metadata={"category": "ai_search", "version": 1},
            )

            retriever = DenseRetriever(session=session)

            # 1. Unfiltered search
            query = RetrievalQuery(
                query_text="What is HNSW vector search?",
                top_k=3,
                score_threshold=0.0,
            )
            result = await retriever.search(query)

            assert result.total_retrieved > 0
            assert len(result.items) > 0
            assert result.items[0].similarity_score > 0.0
            assert result.items[0].parent_text != ""

            # 2. Filtered search by document_id
            filtered_query = RetrievalQuery(
                query_text="HNSW indexes",
                top_k=3,
                filter=MetadataFilter(document_id="doc_retriever_test"),
            )
            filtered_res = await retriever.search(filtered_query)
            assert filtered_res.total_retrieved > 0
            assert all(item.document_id == "doc_retriever_test" for item in filtered_res.items)

            # Cleanup
            await service.delete_document("doc_retriever_test")
