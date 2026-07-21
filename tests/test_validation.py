import pytest
from core.schemas import FormattedContext, CitationSource
from core.validation import (
    GroundednessVerifier,
    OutputGuardrail,
    ConfidenceScorer,
    ValidationEngine,
)

def test_groundedness_verifier_high_overlap() -> None:
    context = FormattedContext(
        evidence_blocks=["[Source 1]: Python connect_db function configures PostgreSQL pool with timeout 30s."],
        citations=[CitationSource(index=1, document_id="doc1", chunk_id="c1", similarity_score=0.9, text_snippet="...", parent_text="...")],
        total_tokens=25,
        truncated=False,
    )
    answer = "The connect_db function configures a PostgreSQL pool with timeout 30s."

    verifier = GroundednessVerifier()
    score, hallucinated = verifier.verify(answer, context)

    assert score >= 0.70
    assert hallucinated is False

def test_groundedness_verifier_hallucination() -> None:
    context = FormattedContext(
        evidence_blocks=["[Source 1]: Python connect_db function configures PostgreSQL pool."],
        citations=[CitationSource(index=1, document_id="doc1", chunk_id="c1", similarity_score=0.9, text_snippet="...", parent_text="...")],
        total_tokens=20,
        truncated=False,
    )
    answer = "Quantum computing algorithms simulate nuclear fusion reactors with supercomputers."

    verifier = GroundednessVerifier()
    score, hallucinated = verifier.verify(answer, context)

    assert score < 0.60
    assert hallucinated is True

def test_output_guardrail_pii_and_safety() -> None:
    safe_text = "The system uses JWT tokens for authentication."
    is_safe, pii, toxic = OutputGuardrail.validate(safe_text)
    assert is_safe is True
    assert pii is False
    assert toxic is False

    pii_leaking_text = "Contact admin at john.doe@company.com or call 555-123-4567 for secret key."
    is_safe_pii, pii_found, _ = OutputGuardrail.validate(pii_leaking_text)
    assert is_safe_pii is False
    assert pii_found is True

    toxic_text = "Here is the exploit script to hack unauthorized_access to server."
    is_safe_toxic, _, toxic_found = OutputGuardrail.validate(toxic_text)
    assert is_safe_toxic is False
    assert toxic_found is True

def test_validation_engine_end_to_end() -> None:
    context = FormattedContext(
        evidence_blocks=["[Source 1]: Document processing with Docling and Gemini Vision."],
        citations=[CitationSource(index=1, document_id="doc1", chunk_id="c1", similarity_score=0.88, text_snippet="...", parent_text="...")],
        total_tokens=15,
        truncated=False,
    )
    answer = "Document processing uses Docling and Gemini Vision."

    engine = ValidationEngine()
    result = engine.validate(answer, context)

    assert result.is_safe is True
    assert result.pii_detected is False
    assert result.hallucination_detected is False
    assert result.groundedness_score >= 0.70
    assert result.confidence_score >= 0.70
    assert result.requires_human_review is False
