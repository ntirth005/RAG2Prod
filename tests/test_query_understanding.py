"""
Tests for the Query Understanding Subsystem (Stage 6).
Tests PIIDetector, IntentClassifier, QueryTransformer (Rewrite, Expansion, HyDE),
and QueryUnderstandingEngine.
"""
import pytest
from unittest.mock import AsyncMock, patch

from core.schemas import QueryComplexity, CanonicalQuery, QueryTrace
from core.query_understanding import (
    PIIDetector,
    IntentClassifier,
    QueryTransformer,
    QueryUnderstandingEngine,
)


# ── PIIDetector Tests ──

def test_pii_detector_clean_query() -> None:
    """Normal query without PII should pass through unchanged."""
    text = "What is the placement rate for computer science?"
    sanitized, pii_safe = PIIDetector.sanitize(text)

    assert pii_safe is True
    assert sanitized == text


def test_pii_detector_redacts_email() -> None:
    """Queries with email addresses should be redacted."""
    text = "Contact john.doe@example.com for placement statistics"
    sanitized, pii_safe = PIIDetector.sanitize(text)

    assert pii_safe is False
    assert "[EMAIL REDACTED]" in sanitized
    assert "john.doe@example.com" not in sanitized


def test_pii_detector_redacts_phone_and_ssn() -> None:
    """Queries with phone or SSN should be redacted."""
    ssn_text = "My SSN is 123-45-6789"
    sanitized_ssn, safe_ssn = PIIDetector.sanitize(ssn_text)

    assert safe_ssn is False
    assert "[SSN REDACTED]" in sanitized_ssn

    phone_text = "Call +1-555-123-4567 regarding my application"
    sanitized_phone, safe_phone = PIIDetector.sanitize(phone_text)

    assert safe_phone is False
    assert "[PHONE REDACTED]" in sanitized_phone


def test_pii_detector_redacts_api_key() -> None:
    """Queries containing API keys should be redacted."""
    text = "Query using sk-proj-1234567890abcdef1234567890abcdef"
    sanitized, pii_safe = PIIDetector.sanitize(text)

    assert pii_safe is False
    assert "[KEY REDACTED]" in sanitized


# ── IntentClassifier Tests ──

def test_intent_classifier_statistical() -> None:
    """Queries containing statistical terms should classify as STATISTICAL & COMPLEX."""
    query = "What is the placement percentage and highest package in 2025?"
    intent, complexity = IntentClassifier.classify(query)

    assert intent == "STATISTICAL"
    assert complexity == QueryComplexity.COMPLEX


def test_intent_classifier_comparative() -> None:
    """Queries asking to compare concepts should classify as COMPARATIVE & COMPLEX."""
    query = "Compare computer science vs electrical engineering course curriculum"
    intent, complexity = IntentClassifier.classify(query)

    assert intent == "COMPARATIVE"
    assert complexity == QueryComplexity.COMPLEX


def test_intent_classifier_simple_factual() -> None:
    """Short factual questions should classify as FACTUAL & SIMPLE."""
    query = "Who is the placement coordinator?"
    intent, complexity = IntentClassifier.classify(query)

    assert intent == "FACTUAL"
    assert complexity == QueryComplexity.SIMPLE


# ── QueryTransformer Tests ──

def test_query_rewrite_simple_acronyms() -> None:
    """Simple query rewriter should expand domain acronyms like ctc and lpa."""
    query = "What is the average ctc and lpa?"
    rewritten = QueryTransformer.rewrite_simple(query)

    assert len(rewritten) == 1
    assert "Cost to Company" in rewritten[0]
    assert "Lakhs Per Annum" in rewritten[0]


@pytest.mark.asyncio
async def test_expand_medium_fallback() -> None:
    """Query Expansion fallback should generate 3 query variations."""
    query = "Explain the campus recruitment process"
    variations = await QueryTransformer.expand_medium(query, llm_client=None)

    assert len(variations) == 3
    assert variations[0] == query
    assert "details and specifications" in variations[1] or "overview" in variations[2]


@pytest.mark.asyncio
async def test_generate_hyde_fallback() -> None:
    """HyDE generation fallback should return a hypothetical document passage."""
    query = "What are the placement rates?"
    hyde_passage, search_queries = await QueryTransformer.generate_hyde(query, llm_client=None)

    assert len(hyde_passage) > 20
    assert "statistics" in hyde_passage.lower() or "document" in hyde_passage.lower()
    assert len(search_queries) == 2
    assert search_queries[0] == query
    assert search_queries[1] == hyde_passage


# ── QueryUnderstandingEngine Tests ──

@pytest.mark.asyncio
async def test_query_understanding_engine_e2e() -> None:
    """Engine should return CanonicalQuery and QueryTrace."""
    engine = QueryUnderstandingEngine(llm_client=None)
    raw_query = "What is the average ctc for CS students?"

    canonical_query, trace = await engine.process(raw_query)

    assert isinstance(canonical_query, CanonicalQuery)
    assert isinstance(trace, QueryTrace)
    assert trace.intent_class == "STATISTICAL"
    assert trace.complexity == QueryComplexity.COMPLEX
    assert trace.pii_safe is True
    assert trace.hyde_passage is not None
    assert len(trace.rewritten_queries) == 2
