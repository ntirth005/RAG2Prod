import asyncio
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

            # Apply score threshold filter in DB (cosine distance <= 1.0 - threshold)
            if query.score_threshold > 0:
                stmt = stmt.where(distance_expr <= (1.0 - query.score_threshold))

            # Retrieve top_k candidate results
            stmt = stmt.limit(query.top_k)

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


# --- Stage 7: Hybrid Retrieval & Reranking Subsystem ---

import re
from core.config import settings
from sqlalchemy import func


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase words/terms for BM25 indexing."""
    return re.findall(r"\w+", text.lower())


class SparseRetriever:
    """
    Sparse keyword retrieval engine using BM25Okapi for exact term matching.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        """Executes a Postgres Full Text Search (FTS) sparse keyword search over stored ChildChunks."""
        with timer_step("retriever", f"Sparse FTS search for query '{query.query_text[:30]}...'"):
            ts_query = func.websearch_to_tsquery('english', query.query_text)
            ts_vector = func.to_tsvector('english', ChildChunk.text)
            rank_score = func.ts_rank_cd(ts_vector, ts_query).label("rank")

            stmt = (
                select(ChildChunk, ParentChunk, rank_score)
                .join(ParentChunk, ChildChunk.parent_id == ParentChunk.id)
                .where(ts_vector.op("@@")(ts_query))
                .order_by(rank_score.desc())
            )

            if query.filter:
                if query.filter.document_id:
                    stmt = stmt.where(ChildChunk.document_id == query.filter.document_id)

                if query.filter.metadata_equals:
                    for key, val in query.filter.metadata_equals.items():
                        stmt = stmt.where(ChildChunk.source_metadata[key].as_json() == val)

            stmt = stmt.limit(query.top_k)
            result = await self.session.execute(stmt)
            rows = result.all()

            if not rows:
                return RetrievalResult(query_text=query.query_text, total_retrieved=0, items=[])

            # Normalize scores for hybrid compatibility
            max_score = max((float(r.rank) for r in rows), default=1.0)
            if max_score <= 0:
                max_score = 1.0

            scored_items = []
            for child, parent, rank in rows:
                norm_score = round(float(rank) / max_score, 4)
                if norm_score < query.score_threshold:
                    continue

                scored_items.append(
                    RetrievalResultItem(
                        chunk_id=child.id,
                        parent_id=child.parent_id,
                        document_id=child.document_id,
                        chunk_text=child.text,
                        parent_text=parent.text,
                        similarity_score=norm_score,
                        rerank_score=norm_score,
                        source_metadata=child.source_metadata or {},
                    )
                )

            info("retriever", f"FTS query returned {len(scored_items)} matching chunks")
            return RetrievalResult(query_text=query.query_text, total_retrieved=len(scored_items), items=scored_items)


class CrossEncoderReranker:
    """
    Reranks candidate retrieval items using cross-encoder relevance scoring.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.RERANKER_MODEL_NAME
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
            except Exception as e:
                info("retriever", f"CrossEncoder model notice ({e}). Using lexical overlap fallback.")
                self._model = False
        return self._model

    async def rerank(self, query_text: str, items: List[RetrievalResultItem], top_k: int) -> List[RetrievalResultItem]:
        """Re-scores candidate items using CrossEncoder model or lexical overlap fallback."""
        if not items:
            return []

        with timer_step("reranker", f"Reranking {len(items)} candidates"):
            model = self._get_model()
            if model:
                pairs = [[query_text, item.chunk_text] for item in items]
                # Run cross-encoder inference in a separate thread to avoid blocking asyncio loop
                scores = await asyncio.to_thread(model.predict, pairs)
                for item, score in zip(items, scores):
                    item.rerank_score = round(float(score), 4)
            else:
                # Lexical overlap fallback for scoring when transformer model is omitted
                q_words = set(_tokenize(query_text))
                for item in items:
                    c_words = set(_tokenize(item.chunk_text))
                    overlap = len(q_words & c_words) / max(len(q_words), 1)
                    item.rerank_score = round(float(item.similarity_score * 0.7 + overlap * 0.3), 4)

            sorted_items = sorted(items, key=lambda x: getattr(x, "rerank_score", x.similarity_score), reverse=True)
            return sorted_items[:top_k]


class HybridRetriever:
    """
    Combines Dense Vector Search, Sparse BM25 Search, Reciprocal Rank Fusion (RRF),
    and Cross-Encoder Reranking.
    """

    def __init__(
        self,
        session: AsyncSession,
        dense_retriever: Optional[DenseRetriever] = None,
        sparse_retriever: Optional[SparseRetriever] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        rrf_k: int = 60,
    ):
        self.session = session
        self.dense = dense_retriever or DenseRetriever(session)
        self.sparse = sparse_retriever or SparseRetriever(session)
        self.reranker = reranker or CrossEncoderReranker()
        self.rrf_k = rrf_k or settings.RRF_K_CONSTANT

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        """
        Executes hybrid retrieval:
        - Mode 'dense': Dense vector search + optional Reranker
        - Mode 'sparse': BM25 keyword search + optional Reranker
        - Mode 'hybrid': Reciprocal Rank Fusion (RRF) of Dense + Sparse + Cross-Encoder Reranking
        """
        if query.mode == "dense":
            res = await self.dense.search(query)
            if query.rerank and settings.ENABLE_RERANKING:
                res.items = await self.reranker.rerank(query.query_text, res.items, query.top_k)
            return res

        if query.mode == "sparse":
            res = await self.sparse.search(query)
            if query.rerank and settings.ENABLE_RERANKING:
                res.items = await self.reranker.rerank(query.query_text, res.items, query.top_k)
            return res

        # Mode == "hybrid" (RRF Fusion)
        with timer_step("retriever", f"Hybrid RRF Search for '{query.query_text[:30]}...'"):
            candidate_k = max(query.top_k * 3, settings.HYBRID_TOP_K_CANDIDATES)
            dense_query = query.model_copy(update={"top_k": candidate_k})
            sparse_query = query.model_copy(update={"top_k": candidate_k})

            dense_res = await self.dense.search(dense_query)
            sparse_res = await self.sparse.search(sparse_query)

            rrf_scores: Dict[str, float] = {}
            chunk_map: Dict[str, RetrievalResultItem] = {}

            # Dense ranks
            for rank, item in enumerate(dense_res.items, start=1):
                chunk_map[item.chunk_id] = item
                rrf_scores[item.chunk_id] = rrf_scores.get(item.chunk_id, 0.0) + (1.0 / (self.rrf_k + rank))

            # Sparse ranks
            for rank, item in enumerate(sparse_res.items, start=1):
                chunk_map[item.chunk_id] = item
                rrf_scores[item.chunk_id] = rrf_scores.get(item.chunk_id, 0.0) + (1.0 / (self.rrf_k + rank))

            # Sort candidate chunks by RRF score
            sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
            candidates = [chunk_map[cid] for cid in sorted_chunk_ids[:candidate_k]]

            # Optional Cross-Encoder Reranking
            if query.rerank and settings.ENABLE_RERANKING:
                final_items = await self.reranker.rerank(query.query_text, candidates, query.top_k)
            else:
                final_items = candidates[:query.top_k]

            info(
                "retriever",
                f"Hybrid search returned {len(final_items)} chunks (Dense={len(dense_res.items)}, Sparse={len(sparse_res.items)})",
            )
            return RetrievalResult(
                query_text=query.query_text,
                total_retrieved=len(final_items),
                items=final_items,
            )

    async def search_multi(
        self,
        query_texts: List[str],
        top_k: int = 5,
        score_threshold: float = 0.0,
        filter_rule: Optional[MetadataFilter] = None,
        mode: str = "hybrid",
        rerank: bool = True,
    ) -> RetrievalResult:
        """
        Executes multi-query hybrid search over query variations (e.g. expansion queries or HyDE).
        Deduplicates matched chunks and reranks top candidates.
        """
        if not query_texts:
            return RetrievalResult(query_text="", total_retrieved=0, items=[])

        merged_items: Dict[str, RetrievalResultItem] = {}
        for q_text in query_texts:
            q_req = RetrievalQuery(
                query_text=q_text,
                top_k=top_k,
                score_threshold=score_threshold,
                filter=filter_rule,
                mode=mode,
                rerank=False,  # Rerank once at the end
            )
            res = await self.search(q_req)
            for item in res.items:
                if item.chunk_id not in merged_items:
                    merged_items[item.chunk_id] = item
                else:
                    if item.similarity_score > merged_items[item.chunk_id].similarity_score:
                        merged_items[item.chunk_id] = item

        sorted_candidates = sorted(merged_items.values(), key=lambda x: x.similarity_score, reverse=True)

        if rerank and settings.ENABLE_RERANKING:
            final_items = await self.reranker.rerank(query_texts[0], sorted_candidates, top_k)
        else:
            final_items = sorted_candidates[:top_k]

        info("retriever", f"Multi-query hybrid search returned {len(final_items)} deduplicated chunks")
        return RetrievalResult(
            query_text=query_texts[0],
            total_retrieved=len(final_items),
            items=final_items,
        )
