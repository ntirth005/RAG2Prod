"""
RAG2Prod — Generation Layer (Stage 5)

Multi-provider LLM client supporting DeepSeek and OpenAI via their
OpenAI-compatible chat completions API. Includes SSE streaming support
and a RAGPipeline orchestrator that chains retrieval → context → generation.
"""
import json
import time
from typing import AsyncGenerator, Optional, Dict, Any, List

import httpx

from core.config import settings
from core.schemas import (
    RetrievalQuery,
    MetadataFilter,
    GenerationResult,
    TokenUsage,
    CitationSource,
    FormattedContext,
    PromptPayload,
    QueryRequest,
    QueryTrace,
)
from core.context_builder import ContextBuilder, PromptBuilder
from core.retriever import DenseRetriever
from core.query_understanding import QueryUnderstandingEngine
from core.prompts import MOCK_GENERATION_PREFIX, INSUFFICIENT_CONTEXT_RESPONSE
from core.logger import info, error as log_error, timer_step

from sqlalchemy.ext.asyncio import AsyncSession


# Provider configuration lookup
_PROVIDER_CONFIG: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "api_key_setting": "DEEPSEEK_API_KEY",
        "model_setting": "DEEPSEEK_MODEL_NAME",
        "base_url_setting": "DEEPSEEK_BASE_URL",
    },
    "openai": {
        "api_key_setting": "OPENAI_API_KEY",
        "model_setting": "OPENAI_MODEL_NAME",
        "base_url_setting": "OPENAI_BASE_URL",
    },
}


class LLMClient:
    """
    Multi-provider LLM client using the OpenAI-compatible chat completions API.
    Supports DeepSeek and OpenAI. Falls back to a mock response when no API key is configured.
    """

    def __init__(
        self,
        provider: str = "deepseek",
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        if provider not in _PROVIDER_CONFIG:
            raise ValueError(f"Unsupported LLM provider: '{provider}'. Choose from: {list(_PROVIDER_CONFIG.keys())}")

        config = _PROVIDER_CONFIG[provider]
        self.provider = provider
        self.api_key = api_key if api_key is not None else getattr(settings, config["api_key_setting"])
        self.model_name = model_name or getattr(settings, config["model_setting"])
        self.base_url = base_url or getattr(settings, config["base_url_setting"])
        self.temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        self.max_tokens = max_tokens or settings.LLM_MAX_OUTPUT_TOKENS

    def _build_request_body(
        self, messages: List[Dict[str, str]], stream: bool = False
    ) -> Dict[str, Any]:
        """Build the OpenAI-compatible chat completions request body."""
        return {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers with Bearer auth."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def generate(self, prompt: PromptPayload) -> tuple[str, TokenUsage]:
        """
        Generate a complete response (non-streaming).
        Returns: (answer_text, token_usage)
        """
        if not self.api_key:
            info("generator", f"No API key for {self.provider} — using mock response")
            return self._mock_response(prompt), TokenUsage()

        messages = [
            {"role": "system", "content": prompt.system_message},
            {"role": "user", "content": prompt.user_message},
        ]

        url = f"{self.base_url}/chat/completions"
        body = self._build_request_body(messages, stream=False)
        headers = self._build_headers()

        with timer_step("generator", f"LLM generation via {self.provider}/{self.model_name}"):
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=body, headers=headers, timeout=60.0)
                response.raise_for_status()
                data = response.json()

        choice = data["choices"][0]
        answer = choice["message"]["content"]

        usage_data = data.get("usage", {})
        token_usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        info("generator", f"Generation complete: {token_usage.total_tokens} tokens used")
        return answer, token_usage

    async def stream(self, prompt: PromptPayload) -> AsyncGenerator[str, None]:
        """
        Stream response tokens via SSE.
        Yields individual text chunks as they arrive.
        """
        if not self.api_key:
            info("generator", f"No API key for {self.provider} — streaming mock response")
            mock_text = self._mock_response(prompt)
            # Simulate streaming by yielding word-by-word
            for word in mock_text.split(" "):
                yield word + " "
            return

        messages = [
            {"role": "system", "content": prompt.system_message},
            {"role": "user", "content": prompt.user_message},
        ]

        url = f"{self.base_url}/chat/completions"
        body = self._build_request_body(messages, stream=True)
        headers = self._build_headers()

        with timer_step("generator", f"LLM streaming via {self.provider}/{self.model_name}"):
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST", url, json=body, headers=headers, timeout=120.0
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload.strip() == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(payload)
                            delta = chunk_data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    @staticmethod
    def _mock_response(prompt: PromptPayload) -> str:
        """Generate a mock response summarizing the context when no LLM API key is available."""
        context_section = prompt.user_message
        return f"{MOCK_GENERATION_PREFIX}{context_section}"


class RAGPipeline:
    """
    End-to-end RAG pipeline orchestrator.
    Chains: QueryUnderstandingEngine → DenseRetriever (multi-query) → ContextBuilder → PromptBuilder → LLMClient
    """

    def __init__(
        self,
        session: AsyncSession,
        provider: str = "deepseek",
    ):
        self.session = session
        self.provider = provider
        self.retriever = DenseRetriever(session=session)
        self.context_builder = ContextBuilder()
        self.prompt_builder = PromptBuilder()

    async def run(self, request: QueryRequest) -> GenerationResult:
        """
        Execute the full RAG pipeline (non-streaming):
        1. Query Understanding (PII, Intent/Complexity, Rewriting/Expansion/HyDE)
        2. Multi-query vector retrieval & deduplication
        3. Context building with citations & token truncation
        4. Prompt assembly & LLM answer generation
        """
        start_time = time.perf_counter()
        provider = request.provider or self.provider

        with timer_step("pipeline", f"Full RAG pipeline for '{request.query_text[:40]}...'"):
            llm = LLMClient(provider=provider)

            # Step 1: Query Understanding
            qu_engine = QueryUnderstandingEngine(llm_client=llm)
            canonical_query, query_trace = await qu_engine.process(request.query_text)

            # Step 2: Multi-query Retrieval
            retrieval_result = await self.retriever.search_multi(
                query_texts=query_trace.rewritten_queries,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
            )

            if not retrieval_result.items:
                latency = (time.perf_counter() - start_time) * 1000
                return GenerationResult(
                    answer=INSUFFICIENT_CONTEXT_RESPONSE,
                    citations=[],
                    token_usage=TokenUsage(),
                    retrieval_count=0,
                    latency_ms=round(latency, 1),
                    model_used=f"{provider}/none",
                    query_trace=query_trace,
                )

            # Step 3: Build context
            context = self.context_builder.build(retrieval_result)

            # Step 4: Assemble prompt
            prompt = self.prompt_builder.build(context, request.query_text)

            # Step 5: Generate answer
            answer, token_usage = await llm.generate(prompt)

            latency = (time.perf_counter() - start_time) * 1000

            return GenerationResult(
                answer=answer,
                citations=context.citations,
                token_usage=token_usage,
                retrieval_count=retrieval_result.total_retrieved,
                latency_ms=round(latency, 1),
                model_used=f"{provider}/{llm.model_name}",
                query_trace=query_trace,
            )

    async def run_stream(
        self, request: QueryRequest
    ) -> tuple[AsyncGenerator[str, None], FormattedContext, str, QueryTrace]:
        """
        Execute the RAG pipeline in streaming mode.
        Returns: (token_stream, context_with_citations, model_identifier, query_trace)
        """
        provider = request.provider or self.provider
        llm = LLMClient(provider=provider)

        # Step 1: Query Understanding
        qu_engine = QueryUnderstandingEngine(llm_client=llm)
        canonical_query, query_trace = await qu_engine.process(request.query_text)

        # Step 2: Multi-query Retrieval
        retrieval_result = await self.retriever.search_multi(
            query_texts=query_trace.rewritten_queries,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )

        if not retrieval_result.items:
            async def empty_stream() -> AsyncGenerator[str, None]:
                yield INSUFFICIENT_CONTEXT_RESPONSE
            return empty_stream(), FormattedContext(), f"{provider}/none", query_trace

        # Step 3: Build context
        context = self.context_builder.build(retrieval_result)

        # Step 4: Assemble prompt
        prompt = self.prompt_builder.build(context, request.query_text)

        # Step 5: Stream answer
        token_stream = llm.stream(prompt)

        return token_stream, context, f"{provider}/{llm.model_id if hasattr(llm, 'model_id') else llm.model_name}", query_trace
