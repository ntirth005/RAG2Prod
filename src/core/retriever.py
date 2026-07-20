from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.models import ChildChunk, ParentChunk
from core.embeddings import EmbeddingClient
from core.schemas import (
    RetrievalQuery,
    RetrievalResult,
    RetrievalResultItem,
    MetadataFilter,
)
from core.logger import info, timer_step


class DenseRetriever:
    """
    Dense vector retrieval engine supporting HNSW Cosine Distance similarity queries,
    parent context joining, and dynamic JSONB metadata filtering.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_client: Optional[EmbeddingClient] = None,
    ):
        self.session = session
        self.embedding_client = embedding_client or EmbeddingClient()

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        """
        Executes a dense similarity search:
        1. Embeds the raw query string into a vector.
        2. Queries ChildChunk using HNSW cosine distance (`<=>`).
        3. Converts distance to similarity score: similarity = 1.0 - cosine_distance.
        4. Applies metadata filters (document_id, JSONB fields).
        5. Joins ParentChunk to provide full parent text context.
        """
        with timer_step("retriever", f"Dense vector search for query '{query.query_text[:30]}...'"):
            query_vector = await self.embedding_client.get_embedding(query.query_text)

            # Cosine distance expression
            distance_expr = ChildChunk.embedding.cosine_distance(query_vector)

            # Build base query with ParentChunk relationship eager load
            stmt = (
                select(ChildChunk, ParentChunk, distance_expr.label("distance"))
                .join(ParentChunk, ChildChunk.parent_id == ParentChunk.id)
                .order_by(distance_expr.asc())
            )

            # Apply Metadata Filters if provided
            if query.filter:
                if query.filter.document_id:
                    stmt = stmt.where(ChildChunk.document_id == query.filter.document_id)

                if query.filter.metadata_equals:
                    for key, val in query.filter.metadata_equals.items():
                        # PostgreSQL JSONB key matching
                        stmt = stmt.where(ChildChunk.source_metadata[key].as_json() == val)

            # Retrieve top_k candidate results
            # Fetch up to top_k * 2 to account for score threshold filtering
            fetch_limit = max(query.top_k * 2, 20)
            stmt = stmt.limit(fetch_limit)

            result = await self.session.execute(stmt)
            rows = result.all()

            items: List[RetrievalResultItem] = []
            for child, parent, distance in rows:
                sim_score = max(0.0, 1.0 - float(distance))
                if sim_score < query.score_threshold:
                    continue

                items.append(
                    RetrievalResultItem(
                        chunk_id=child.id,
                        parent_id=child.parent_id,
                        document_id=child.document_id,
                        chunk_text=child.text,
                        parent_text=parent.text,
                        similarity_score=round(sim_score, 4),
                        source_metadata=child.source_metadata or {},
                    )
                )

                if len(items) >= query.top_k:
                    break

            info("retriever", f"Query returned {len(items)} matching chunks")
            return RetrievalResult(
                query_text=query.query_text,
                total_retrieved=len(items),
                items=items,
            )

    async def search_multi(
        self,
        query_texts: List[str],
        top_k: int = 5,
        score_threshold: float = 0.0,
        filter_rule: Optional[MetadataFilter] = None,
    ) -> RetrievalResult:
        """
        Executes vector searches for multiple query strings (e.g. rewritten/expanded queries or HyDE passage).
        Merges and deduplicates matched chunks by chunk_id, keeping the maximum similarity score.
        """
        if not query_texts:
            return RetrievalResult(query_text="", total_retrieved=0, items=[])

        if len(query_texts) == 1:
            single_q = RetrievalQuery(
                query_text=query_texts[0],
                top_k=top_k,
                score_threshold=score_threshold,
                filter=filter_rule,
            )
            return await self.search(single_q)

        with timer_step("retriever", f"Multi-query vector search ({len(query_texts)} variations)"):
            merged_items: Dict[str, RetrievalResultItem] = {}

            for q_text in query_texts:
                req = RetrievalQuery(
                    query_text=q_text,
                    top_k=top_k,
                    score_threshold=score_threshold,
                    filter=filter_rule,
                )
                res = await self.search(req)

                for item in res.items:
                    if item.chunk_id not in merged_items:
                        merged_items[item.chunk_id] = item
                    else:
                        # Keep the higher similarity score across query variations
                        if item.similarity_score > merged_items[item.chunk_id].similarity_score:
                            merged_items[item.chunk_id] = item

            # Sort merged items by similarity score descending
            sorted_items = sorted(
                merged_items.values(),
                key=lambda x: x.similarity_score,
                reverse=True,
            )[:top_k]

            info("retriever", f"Multi-query returned {len(sorted_items)} deduplicated matching chunks")
            return RetrievalResult(
                query_text=query_texts[0],
                total_retrieved=len(sorted_items),
                items=sorted_items,
            )
