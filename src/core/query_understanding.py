"""
RAG2Prod — Query Understanding Subsystem (Stage 6)

Analyzes and standardizes incoming queries by scanning for PII,
classifying user intent and complexity (SIMPLE, MEDIUM, COMPLEX),
and dynamically applying Query Rewriting, Query Expansion, or HyDE (Hypothetical Document Embeddings).
"""
import re
from typing import List, Tuple, Optional, Dict, Any
from uuid import uuid4

from core.schemas import (
    QueryComplexity,
    CanonicalQuery,
    QueryTrace,
)
from core.logger import info, timer_step


# ─── PII Detector ───────────────────────────────────────────────────

class PIIDetector:
    """
    Scans query text for sensitive Personal Identifiable Information (PII)
    and redacts matches to ensure privacy compliance.
    """

    PATTERNS: List[Tuple[str, re.Pattern, str]] = [
        ("EMAIL", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE), "[EMAIL REDACTED]"),
        ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN REDACTED]"),
        ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[CREDIT CARD REDACTED]"),
        ("PHONE", re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE REDACTED]"),
        ("API_KEY", re.compile(r"\b(?:sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{36})\b"), "[KEY REDACTED]"),
    ]

    @classmethod
    def sanitize(cls, text: str) -> Tuple[str, bool]:
        """
        Scans text for PII patterns.
        Returns: (sanitized_text, pii_safe)
        """
        sanitized = text
        pii_found = False

        for name, pattern, replacement in cls.PATTERNS:
            if pattern.search(sanitized):
                pii_found = True
                sanitized = pattern.sub(replacement, sanitized)

        if pii_found:
            info("query_understanding", "PII detected and redacted in user query")

        return sanitized, not pii_found


# ─── Intent & Complexity Classifier ─────────────────────────────────

class IntentClassifier:
    """
    Classifies user intent and assigns complexity routing levels:
    - SIMPLE: Direct factual/keyword questions -> Query Rewriting
    - MEDIUM: Multi-concept/comparative questions -> Query Expansion
    - COMPLEX: Statistical/tabular/implicit questions -> HyDE Generation
    """

    STATISTICAL_KEYWORDS = {
        "rate", "percentage", "statistics", "package", "salary", "lpa", "ctc",
        "count", "number", "highest", "average", "lowest", "ratio", "%", "numbers",
        "placements", "placed", "stats", "figures", "data", "metrics"
    }

    COMPARATIVE_KEYWORDS = {
        "vs", "versus", "compare", "comparison", "difference", "better", "worse",
        "different", "distinguish", "pros and cons"
    }

    SUMMARIZATION_KEYWORDS = {
        "summarize", "summary", "overview", "brief", "key points", "highlights", "takeaways"
    }

    CONCEPTUAL_KEYWORDS = {
        "why", "how", "explain", "architecture", "concept", "workflow", "process", "mechanism"
    }

    @classmethod
    def classify(cls, query: str) -> Tuple[str, QueryComplexity]:
        """
        Classifies query into intent class and complexity routing level.
        Returns: (intent_class, QueryComplexity)
        """
        lower_query = query.lower()
        words = set(re.findall(r"\b\w+\b", lower_query))

        # Determine Intent
        if words.intersection(cls.STATISTICAL_KEYWORDS) or "%" in query:
            intent = "STATISTICAL"
        elif words.intersection(cls.COMPARATIVE_KEYWORDS):
            intent = "COMPARATIVE"
        elif words.intersection(cls.SUMMARIZATION_KEYWORDS):
            intent = "SUMMARIZATION"
        elif words.intersection(cls.CONCEPTUAL_KEYWORDS):
            intent = "CONCEPTUAL"
        else:
            intent = "FACTUAL"

        # Determine Complexity Level
        word_count = len(query.split())

        if intent in ("STATISTICAL", "COMPARATIVE") or word_count > 15:
            complexity = QueryComplexity.COMPLEX
        elif intent in ("CONCEPTUAL", "SUMMARIZATION") or word_count > 8:
            complexity = QueryComplexity.MEDIUM
        else:
            complexity = QueryComplexity.SIMPLE

        info("query_understanding", f"Classified query: intent={intent}, complexity={complexity.value}")
        return intent, complexity


# ─── Query Transformer (Rewriting, Expansion, HyDE) ─────────────────

class QueryTransformer:
    """
    Transforms queries based on complexity routing:
    - Simple: Normalizes phrasing and expands domain acronyms.
    - Medium: Generates 3 query variations (Query Expansion).
    - Complex: Generates a hypothetical answer passage (HyDE).
    """

    ACRONYM_MAP = {
        "ctc": "Cost to Company salary package",
        "lpa": "Lakhs Per Annum package salary",
        "t&p": "Training and Placement cell",
        "tnp": "Training and Placement cell",
        "hr": "Human Resources recruitment",
        "cpi": "Cumulative Performance Index GPA",
        "cgpa": "Cumulative Grade Point Average",
        "rag": "Retrieval Augmented Generation",
    }

    @classmethod
    def rewrite_simple(cls, query: str) -> List[str]:
        """Query Rewriting for SIMPLE queries: expands acronyms & cleans whitespace."""
        words = query.split()
        rewritten_words = []
        for word in words:
            clean_word = word.strip(".,!?()").lower()
            if clean_word in cls.ACRONYM_MAP:
                rewritten_words.append(cls.ACRONYM_MAP[clean_word])
            else:
                rewritten_words.append(word)

        rewritten = " ".join(rewritten_words)
        return [rewritten]

    @classmethod
    async def expand_medium(cls, query: str, llm_client: Optional[Any] = None) -> List[str]:
        """
        Query Expansion for MEDIUM queries:
        Generates 3 search variations to cover synonyms and perspectives.
        """
        variations = [query]

        if llm_client and getattr(llm_client, "api_key", None):
            try:
                from core.schemas import PromptPayload
                prompt = PromptPayload(
                    system_message=(
                        "You are an expert search query expander. "
                        "Given a user search query, generate exactly 2 alternative, rephrased search queries "
                        "that use synonyms, related technical terms, or different search perspectives. "
                        "Output ONLY the 2 alternative queries, one per line. Do NOT include numbers or markdown."
                    ),
                    user_message=f"Original Query: {query}",
                    context_tokens=50,
                )
                answer, _ = await llm_client.generate(prompt)
                lines = [line.strip("- *123456789. ") for line in answer.splitlines() if line.strip()]
                for line in lines[:2]:
                    if line and line not in variations:
                        variations.append(line)
            except Exception as e:
                info("query_understanding", f"LLM expansion fallback due to: {e}")

        if len(variations) < 3:
            # Fallback heuristic expansion
            variations.append(f"{query} details and specifications")
            variations.append(f"{query} overview summary")

        return variations[:3]

    @classmethod
    async def generate_hyde(cls, query: str, llm_client: Optional[Any] = None) -> Tuple[str, List[str]]:
        """
        HyDE (Hypothetical Document Embeddings) for COMPLEX queries:
        Generates a hypothetical passage that directly answers the question.
        Embedding this passage matches target document chunks better than raw queries.

        Returns: (hyde_passage, list_of_search_queries_including_hyde)
        """
        if llm_client and getattr(llm_client, "api_key", None):
            try:
                from core.schemas import PromptPayload
                prompt = PromptPayload(
                    system_message=(
                        "You are a helpful domain expert. "
                        "Write a brief, realistic 2-3 sentence hypothetical excerpt from a professional document or report "
                        "that directly answers the user's question. Include specific statistical phrasing, metrics, "
                        "and numbers if applicable. Output ONLY the excerpt text."
                    ),
                    user_message=f"Question: {query}",
                    context_tokens=50,
                )
                hyde_passage, _ = await llm_client.generate(prompt)
                hyde_passage = hyde_passage.strip()
                search_queries = [query, hyde_passage]
                return hyde_passage, search_queries
            except Exception as e:
                info("query_understanding", f"LLM HyDE fallback due to: {e}")

        # Fallback heuristic HyDE passage
        heuristic_hyde = (
            f"The document details comprehensive statistics and records regarding {query}. "
            f"Key metrics, percentage figures, and reports indicate specific performance data and official results."
        )
        return heuristic_hyde, [query, heuristic_hyde]


# ─── Query Understanding Engine (Main Orchestrator) ─────────────────

class QueryUnderstandingEngine:
    """
    Main orchestrator for the Query Understanding Subsystem.
    Preprocesses query -> PII check -> Intent & Complexity -> Rewriting/Expansion/HyDE.
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    async def process(self, raw_query: str) -> Tuple[CanonicalQuery, QueryTrace]:
        """
        Processes a raw user query and returns (CanonicalQuery, QueryTrace).
        """
        with timer_step("query_understanding", f"Processing query: '{raw_query[:30]}...'"):
            # Step 1: PII Detection & Redaction
            sanitized_query, pii_safe = PIIDetector.sanitize(raw_query)

            # Step 2: Intent & Complexity Classification
            intent_class, complexity = IntentClassifier.classify(sanitized_query)

            # Step 3: Query Transformation
            hyde_passage: Optional[str] = None

            if complexity == QueryComplexity.SIMPLE:
                rewritten_queries = QueryTransformer.rewrite_simple(sanitized_query)
            elif complexity == QueryComplexity.MEDIUM:
                rewritten_queries = await QueryTransformer.expand_medium(sanitized_query, self.llm_client)
            else:  # COMPLEX
                hyde_passage, rewritten_queries = await QueryTransformer.generate_hyde(sanitized_query, self.llm_client)

            canonical_text = rewritten_queries[0] if rewritten_queries else sanitized_query

            canonical_query = CanonicalQuery(
                query_id=uuid4(),
                canonical_text=canonical_text,
                intent_class=intent_class,
                complexity=complexity,
                rewritten_queries=rewritten_queries,
                pii_safe=pii_safe,
            )

            query_trace = QueryTrace(
                intent_class=intent_class,
                complexity=complexity,
                pii_safe=pii_safe,
                sanitized_query=sanitized_query,
                rewritten_queries=rewritten_queries,
                hyde_passage=hyde_passage,
            )

            return canonical_query, query_trace
