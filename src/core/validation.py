"""
RAG2Prod — Validation Layer & Output Guardrails (Stage 8)

Validates generated LLM responses before delivery:
1. Groundedness Verification: Measures N-gram & claim token overlap between answer and evidence blocks.
2. Anti-Hallucination Detection: Flags ungrounded claims when groundedness score falls below threshold.
3. Output Guardrails: Scans generated text for PII leaks and toxic keywords.
4. Confidence Scoring & Human Review Routing: Calculates composite confidence score and gates low-confidence answers.
"""
import re
from typing import List, Tuple, Optional
from core.schemas import ValidationResult, FormattedContext, CitationSource
from core.query_understanding import PIIDetector
from core.logger import info, timer_step

TOXIC_KEYWORDS = {
    "hack", "exploit", "malware", "bypassed", "unauthorized_access",
    "stolen_key", "leak_secret"
}

def _extract_word_tokens(text: str) -> set:
    """Extract lowercase word tokens (length >= 3) excluding common stop words."""
    words = re.findall(r"\b[a-zA-Z0-9_]{3,}\b", text.lower())
    stop_words = {"the", "and", "for", "with", "this", "that", "from", "are", "was", "were", "been", "have", "has", "not", "your", "can", "will"}
    return {w for w in words if w not in stop_words}


class GroundednessVerifier:
    """
    Evaluates groundedness of generated LLM answer against retrieved evidence context.
    """

    def __init__(self, hallucination_threshold: float = 0.60):
        self.hallucination_threshold = hallucination_threshold

    def verify(self, answer: str, context: FormattedContext) -> Tuple[float, bool]:
        """
        Computes groundedness_score (0.0 to 1.0) and hallucination_detected flag.
        """
        if not answer or not context.evidence_blocks:
            return 0.0, True

        answer_tokens = _extract_word_tokens(answer)
        if not answer_tokens:
            return 1.0, False

        # Combine all evidence blocks into one context token set
        combined_evidence = " ".join(context.evidence_blocks)
        evidence_tokens = _extract_word_tokens(combined_evidence)

        if not evidence_tokens:
            return 0.0, True

        # Overlap ratio: how many answer key tokens appear in the retrieved evidence
        matched_tokens = answer_tokens.intersection(evidence_tokens)
        groundedness_score = round(len(matched_tokens) / len(answer_tokens), 4)

        hallucination_detected = groundedness_score < self.hallucination_threshold
        info("validation", f"Groundedness score: {groundedness_score}, hallucination_detected: {hallucination_detected}")
        return groundedness_score, hallucination_detected


class OutputGuardrail:
    """
    Scans generated LLM response for PII leaks and toxic content.
    """

    @classmethod
    def validate(cls, text: str) -> Tuple[bool, bool, bool]:
        """
        Returns: (is_safe, pii_detected, toxicity_detected)
        """
        if not text:
            return True, False, False

        # PII Check using PIIDetector
        _, pii_safe = PIIDetector.sanitize(text)
        pii_detected = not pii_safe

        # Toxicity & Unsafe keyword check
        text_words = set(re.findall(r"\b\w+\b", text.lower()))
        toxicity_detected = len(text_words.intersection(TOXIC_KEYWORDS)) > 0

        is_safe = (not pii_detected) and (not toxicity_detected)
        info("validation", f"Output Guardrail: safe={is_safe}, pii_detected={pii_detected}, toxicity={toxicity_detected}")
        return is_safe, pii_detected, toxicity_detected


class ConfidenceScorer:
    """
    Computes system confidence score (0.0 to 1.0) and determines human review routing.
    """

    def __init__(self, review_threshold: float = 0.70):
        self.review_threshold = review_threshold

    def calculate(
        self,
        groundedness_score: float,
        is_safe: bool,
        citations: List[CitationSource],
        hallucination_detected: bool,
    ) -> Tuple[float, bool]:
        """
        Computes composite confidence score and returns (confidence_score, requires_human_review).
        """
        if not is_safe or hallucination_detected:
            # Unsafe or hallucinated outputs automatically require human review
            return round(min(groundedness_score, 0.49), 4), True

        avg_similarity = (
            sum(c.similarity_score for c in citations) / len(citations)
            if citations else 0.5
        )

        # Composite score formula: 50% groundedness + 50% retrieval similarity
        confidence_score = round(0.50 * groundedness_score + 0.50 * avg_similarity, 4)
        requires_review = confidence_score < self.review_threshold

        info("validation", f"Calculated confidence_score={confidence_score}, requires_human_review={requires_review}")
        return confidence_score, requires_review


class ValidationEngine:
    """
    Main orchestrator for Stage 8 Validation Layer & Output Guardrails.
    """

    def __init__(
        self,
        groundedness_verifier: Optional[GroundednessVerifier] = None,
        confidence_scorer: Optional[ConfidenceScorer] = None,
    ):
        self.verifier = groundedness_verifier or GroundednessVerifier()
        self.confidence_scorer = confidence_scorer or ConfidenceScorer()

    def validate(self, answer: str, context: FormattedContext) -> ValidationResult:
        """
        Executes complete validation checks on an LLM answer and returns ValidationResult.
        """
        with timer_step("validation", "Executing Validation Layer & Output Guardrails"):
            groundedness_score, hallucination_detected = self.verifier.verify(answer, context)
            is_safe, pii_detected, toxicity_detected = OutputGuardrail.validate(answer)
            confidence_score, requires_human_review = self.confidence_scorer.calculate(
                groundedness_score=groundedness_score,
                is_safe=is_safe,
                citations=context.citations,
                hallucination_detected=hallucination_detected,
            )

            return ValidationResult(
                is_safe=is_safe,
                pii_detected=pii_detected,
                toxicity_detected=toxicity_detected,
                groundedness_score=groundedness_score,
                hallucination_detected=hallucination_detected,
                confidence_score=confidence_score,
                requires_human_review=requires_human_review,
            )
