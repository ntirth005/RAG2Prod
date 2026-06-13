# Reference Guide: Document Chunking Methodologies

This document serves as a research guide for understanding, comparing, and choosing chunking strategies for the RAG ingestion pipeline.

---

## Summary Comparison Matrix

| Methodology | Primary Split Trigger | Ingestion Speed | API Cost | Best Used For |
| :--- | :--- | :--- | :--- | :--- |
| **Fixed-Size** | Absolute character/word count | Instant | None | Simple text, quick prototyping |
| **Recursive Character** | Token/Char length delimiters (`\n\n`, `\n`, ` `) | Ultra Fast | None | General plain text, standard Markdown |
| **Token-Based** | Tokenizer token counts (e.g., `cl100k_base`) | Very Fast | None (Local) | Standardizing inputs to specific LLMs |
| **Sentence-Level** | Sentence boundary detectors (NLTK/SpaCy) | Fast | None | Highly granular retrieval, sentence-search |
| **Sliding Window** | Rolling index with stride step size | Fast | None | Retaining heavy local context between blocks |
| **Syntax-Specific** | Format syntax markers (Markdown/Code/LaTeX) | Fast | None | Code repositories, technical manuals |
| **Entity/Element-Based** | Domain entities (e.g., menu items, legal clauses) | Medium | Low | Highly structured tabular/listed data |
| **Semantic (Embedding)** | Semantic distance (cosine similarity) threshold | Slow | High | Unstructured narratives, transcripts, logs |
| **Layout/Structure-Aware** | Document structural nodes (headers, tables) | Medium | Low | PDFs, Word Docs, financial sheets |
| **Parent-Child (Hierarchical)** | Nested sizes (e.g., 1000 parent / 200 child tokens) | Fast | None | High-detail manuals, exact-reference Q&A |
| **Contextual Chunking** | LLM-generated global context prefixing | Slow | Medium | High-accuracy retrieval on small chunks |
| **Cluster-Based** | Spatial document-wide topic clustering (K-Means) | Slow | High | Document syntheses, topic-wide summarizations |
| **Multimodal Chunking** | Visual layouts + spatial bounding boxes | Slow | High | Presentations (PPTs), heavily illustrated manuals |
| **Agentic / LLM-Based** | LLM-defined conceptual boundaries | Very Slow | Very High | Complex, multi-topic historical documents |

---

## 1. Fixed-Size Chunking (Naive)
**Common Aliases:** *Fixed-length Chunking, Naive Character Splitting, Static Window Chunking*

Splits text strictly at a fixed number of characters or words, ignoring formatting, sentence endings, and words.

* **Pros:** Extremely fast and simple to implement.
* **Cons:** Often breaks words or sentences in half, causing major loss of semantic meaning at chunk boundaries.
* **Best For:** Quick prototyping or testing pipeline connectivity.

---

## 2. Recursive Character Chunking
**Common Aliases:** *Recursive Splitting, Delimiter-Based Chunking, Hierarchical Separator Splitter*

The standard baseline for RAG. It splits text using a hierarchical list of characters (typically `["\n\n", "\n", " ", ""]`), trying to keep paragraphs, sentences, and words together in that order.

* **Pros:** Highly performant, requires no external API calls, predictable maximum size.
* **Cons:** Blind to semantic meaning and document layout. Can still split code blocks or tables awkwardly if they exceed the size limit.
* **Overlap Strategy:** Relies on a static overlap (e.g., 10–20%) to share context across boundaries.

---

## 3. Token-Based Chunking
**Common Aliases:** *Token Splitting, LLM-Aligned Chunking, Model-Specific Segmenting*

Splits text based on the count of tokens from a specific LLM tokenizer (such as OpenAI's `tiktoken` or Hugging Face tokenizers) rather than character or word counts.

* **Pros:** Guarantees chunks fit exactly within the model's token limits without estimation errors (since 1 character $\neq$ 1 token).
* **Cons:** Can still split words or sentences awkwardly if token limits are hit.
* **Best For:** Systems where exact token budgeting is critical.

---

## 4. Sentence-Level Chunking
**Common Aliases:** *Sentence Boundary Chunking, Grammatical Segmenting, Sentence-by-Sentence Splitting*

Splits text strictly at sentence boundaries, using NLP sentence splitters (like NLTK, SpaCy, or regex).

* **Pros:** Every chunk is a grammatically complete statement, preventing awkward breaks mid-thought.
* **Cons:** Chunks can be too small to contain meaningful context for the LLM. Often requires pairing with a sliding window or parent-child retrieval.

---

## 5. Sliding Window (Rolling/Overlap) Chunking
**Common Aliases:** *Rolling Window Chunking, Overlapping Chunking, Sliding Window Splits, N-Gram Word Windows*

Creates overlapping chunks by moving a window of size $N$ forward by a stride of $S$ (where $S < N$).

* **Pros:** Ensures that any semantic transition that happens near a chunk boundary is fully captured in at least one of the overlapping chunks.
* **Cons:** Generates redundant information, which increases index size and storage costs.

---

## 6. Syntax-Specific (Markdown, Code, LaTeX) Chunking
**Common Aliases:** *Code Chunking, Markdown Splitter, Tree-Sitter Chunking, Language-Parser Splitting*

Uses the syntax tree of a specific programming language or formatting markup to define boundaries.

* **Pros:** Keeps entire code classes, functions, markdown lists, or mathematical equations whole within single chunks.
* **Cons:** Fails if the document has syntax errors or isn't well-formatted.
* **Best For:** Technical documentation, developer wikis, and code RAG.

---

## 7. Entity/Element-Based Chunking
**Common Aliases:** *Node-Based Chunking, Block-Based Ingestion, Schema-Aware Chunking, Entity-Aligned Splits*

Splits text by identifying specific business entities or logical elements (e.g., a menu item, a drug profile in a medical database, or a legal clause).

* **Pros:** Extremely high precision. Keeps associated fields (like Name, Price, and Ingredients) grouped together.
* **Cons:** Highly customized; requires writing custom parsers for each specific document type.

---

## 8. Semantic (Embedding-Based) Chunking
**Common Aliases:** *Embedding-Based Chunking, Semantic Similarity Splitting, Dynamic Semantic Segmenting*

Groups text based on conceptual similarity instead of token or character counts.

### The Algorithm
1. Split the text into sentences.
2. Generate an embedding vector for each sentence.
3. Compute the cosine similarity between sentence $i$ and sentence $i+1$.
4. Set a threshold (e.g., a drop in similarity greater than $1.5 \times$ the standard deviation).
5. Split the text into a new chunk whenever similarity drops below the threshold.

* **Pros:** Chunks represent singular topics or thoughts; extremely coherent.
* **Cons:** High latency and API cost. Size of chunks is unpredictable (can exceed maximum context limits of downstream models).

---

## 9. Layout/Structure-Aware Chunking
**Common Aliases:** *Layout-Parser Chunking, Document-Structure Chunking, Visual Ingestion, Document Hierarchy Parsing*

Uses document formatting (visual layout, HTML/Markdown nodes) to establish chunks.

* **Pros:** Preserves relationship context (e.g., keeps table rows and item-price associations intact).
* **Cons:** Dependent on parser accuracy; parsing scanned documents or complex PDFs can be slow and prone to errors.

---

## 10. Parent-Child (Hierarchical) Chunking
**Common Aliases:** *Hierarchical Chunking, Small-to-Large Retrieval, Parent-Child Mapping, Sub-chunking, Multi-vector Retriever Mapping*

Decouples the text used for **vector matching** from the text used for **generation**.

* **Pros:** Small chunks are easier to match semantically; parent chunks ensure the LLM has complete context with no orphaned spillovers.
* **Cons:** Requires managing mapping relations in the storage layer.

---

## 11. Contextual Chunking (Augmented Embedding)
**Common Aliases:** *Contextual Retrieval (Anthropic), Context-Augmented Chunking, Augmented Embeddings, Self-Contextualizing Chunking*

Prepends a short, LLM-generated document-wide context to individual chunks before embedding and indexing.

### The Algorithm
1. Split the document into standard chunks (e.g., 200 tokens).
2. Generate a global summary of the whole document (or main section).
3. Use an LLM to generate a 1–2 sentence contextual bridge for each chunk.
4. Prepend the contextual bridge to the chunk text and embed the combined string.
5. Store the original raw chunk text for LLM generation, but use the augmented text embedding for search.

* **Pros:** Dramatically improves retrieval accuracy for small chunks without losing the global thread.
* **Cons:** Incurs LLM API call cost per chunk during ingestion.

---

## 12. Cluster-Based (K-Means) Chunking
**Common Aliases:** *K-Means Chunking, Topic-Clustered Ingestion, Semantic Clustering, Non-Sequential Topic Grouping*

Groups non-adjacent sentences or blocks across the entire document into single chunks based on topic similarity.

* **Pros:** Captures scattered references to the same topic in a single retrieval node.
* **Cons:** Disrupts sequential flow, which can confuse downstream generation LLMs if not post-processed.

---

## 13. Multimodal Chunking
**Common Aliases:** *Visual Chunking, Spatial Layout Chunking, PDF-Screenshot Chunking, Multi-media Segmenting*

Chunks documents containing both visual (images, diagrams) and text media.

* **Pros:** Captures diagrams, charts, and illustrations that text-only splitters miss.
* **Cons:** Requires multimodal models (VDMs) or heavy OCR, causing high processing costs.

---

## 14. Agentic / LLM-Based Chunking
**Common Aliases:** *LLM-Guided Splitting, Self-Segmenting Text, Agentic Segmentation, Dynamic AI Chunking*

Uses an LLM as a "decision maker" to read the document page by page and determine where to split.

* **Pros:** Unmatched semantic precision, handles complex structural contexts easily.
* **Cons:** Prohibitively expensive and slow for large-scale production ingestion.
