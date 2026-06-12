# RAG2Prod
Building an Agentic RAG System from Prototype to Production

## System Design

### High Level Architecture
```mermaid
flowchart LR

%% =====================================================
%% USER LAYER
%% =====================================================

User([User])

%% =====================================================
%% SECURITY
%% =====================================================

subgraph Security_and_Access_Control
    Auth[Authentication]
    RBAC[Authorization / RBAC]
    InputPII[Input PII Detection]
    RateLimit[Rate Limiting]
end

%% =====================================================
%% QUERY UNDERSTANDING
%% =====================================================

subgraph Query_Understanding
    Intent[Intent Classification]

    Complexity{Query Complexity}

    Rewrite[Query Rewriting]

    Expansion[Query Expansion]

    HyDE[HyDE Generation]

    MultiQuery[Multi Query Generation]

    CanonicalQuery[Canonical Query]
end

%% =====================================================
%% CACHE
%% =====================================================

subgraph Cache_Layer
    SemanticCache[Semantic Query Cache]
    ResponseCache[Response Cache]
end

%% =====================================================
%% RETRIEVAL
%% =====================================================

subgraph Hybrid_Retrieval
    Dense[Dense Retrieval]

    Sparse[BM25 Retrieval]

    Graph[Knowledge Graph Retrieval]

    MetadataFilter[Metadata Filtering]

    Fusion[Hybrid Fusion]

    Reranker[Cross Encoder Reranker]

    Compression[Context Compression]

    Dedup[Context Deduplication]
end

%% =====================================================
%% KNOWLEDGE STORES
%% =====================================================

subgraph Knowledge_Stores
    VectorDB[(Vector Database)]

    Postgres[(Postgres Database)]

    KG[(Knowledge Graph)]

    ObjectStore[(Object Storage)]
end

%% =====================================================
%% AGENTIC REASONING
%% =====================================================

subgraph Agentic_Reasoning
    Planner[Task Planner]

    Decompose[Task Decomposition]

    ToolSelect[Tool Selection]

    ToolExec[Tool Execution]

    ToolFailure{Tool Failed?}

    NeedMore{Need More Evidence?}

    Evidence[Evidence Aggregation]
end

%% =====================================================
%% CONTEXT ENGINEERING
%% =====================================================

subgraph Context_Engineering
    ContextBuilder[Context Builder]

    CitationBuilder[Citation Builder]

    PromptBuilder[Prompt Builder]
end

%% =====================================================
%% GENERATION
%% =====================================================

subgraph Generation
    LLM[Reasoning LLM]

    StructuredOutput[Structured Output]
end

%% =====================================================
%% OUTPUT SAFETY
%% =====================================================

subgraph Output_Guardrails
    OutputPII[Output PII Detection]

    PolicyCheck[Policy Validation]

    Toxicity[Toxicity Detection]

    Safety[Safety Validation]
end

%% =====================================================
%% VALIDATION
%% =====================================================

subgraph Validation
    Grounding[Grounding Verification]

    Hallucination[Hallucination Detection]

    Consistency[Consistency Check]

    Confidence[Confidence Scoring]
end

%% =====================================================
%% HUMAN REVIEW
%% =====================================================

subgraph Human_in_the_Loop
    HumanReview[Human Review Queue]

    Approved[Human Approved Response]
end

%% =====================================================
%% DELIVERY
%% =====================================================

subgraph Response_Delivery
    Streaming[Streaming Layer]

    FinalResponse[Final Response]
end

%% =====================================================
%% OBSERVABILITY
%% =====================================================

subgraph Observability
    Tracing[Distributed Tracing]

    Logs[Centralized Logging]

    Latency[Latency Metrics]

    Cost[Cost Monitoring]

    Tokens[Token Usage Analytics]
end

%% =====================================================
%% EVALUATION
%% =====================================================

subgraph Evaluation
    Precision[Retrieval Precision]

    Recall[Retrieval Recall]

    Faithfulness[Faithfulness]

    Relevance[Answer Relevance]

    LLMJudge[LLM Judge]

    Benchmark[Benchmark Suite]

    RedTeam[Red Team Testing]
end

%% =====================================================
%% CONTINUOUS IMPROVEMENT
%% =====================================================

subgraph Continuous_Improvement
    Feedback[Feedback Store]

    RetrievalTuning[Retrieval Tuning]

    PromptTuning[Prompt Optimization]

    AgentTuning[Agent Optimization]

    GuardrailTuning[Guardrail Updates]

    KnowledgeUpdates[Knowledge Updates]

    FineTune[Fine Tuning Dataset]
end

%% =====================================================
%% MAIN REQUEST FLOW
%% =====================================================

User --> Auth
Auth --> RBAC
RBAC --> InputPII
InputPII --> RateLimit

RateLimit --> Intent

Intent --> Complexity

Complexity -->|Simple| Rewrite

Complexity -->|Medium| Expansion

Complexity -->|Complex| HyDE

Rewrite --> CanonicalQuery

Expansion --> CanonicalQuery

HyDE --> MultiQuery

MultiQuery --> CanonicalQuery

CanonicalQuery --> SemanticCache

SemanticCache -->|Cache Hit| Streaming

SemanticCache -->|Cache Miss| Dense

%% =====================================================
%% RETRIEVAL FLOW
%% =====================================================

CanonicalQuery --> Dense
CanonicalQuery --> Sparse
CanonicalQuery --> Graph

VectorDB --> Dense

Postgres --> Sparse

KG --> Graph

Dense --> MetadataFilter
Sparse --> MetadataFilter
Graph --> MetadataFilter

MetadataFilter --> Fusion

Fusion --> Reranker

Reranker --> Compression

Compression --> Dedup

Dedup --> Planner

%% =====================================================
%% AGENT FLOW
%% =====================================================

Planner --> Decompose

Decompose --> ToolSelect

ToolSelect --> ToolExec

ObjectStore --> ToolExec

ToolExec --> ToolFailure

ToolFailure -->|Yes| Planner

ToolFailure -->|No| NeedMore

NeedMore -->|Yes| Dense

NeedMore -->|No| Evidence

Evidence --> ContextBuilder

%% =====================================================
%% GENERATION FLOW
%% =====================================================

ContextBuilder --> CitationBuilder

CitationBuilder --> PromptBuilder

PromptBuilder --> LLM

LLM --> StructuredOutput

StructuredOutput --> OutputPII

OutputPII --> PolicyCheck

PolicyCheck --> Toxicity

Toxicity --> Safety

Safety --> Grounding

Grounding --> Hallucination

Hallucination --> Consistency

Consistency --> Confidence

%% =====================================================
%% CONFIDENCE DECISION
%% =====================================================

Confidence --> Decision{Confidence OK?}

Decision -->|High| ResponseCache

Decision -->|Low| HumanReview

HumanReview --> Approved

Approved --> ResponseCache

%% =====================================================
%% DELIVERY
%% =====================================================

ResponseCache --> Streaming

Streaming --> FinalResponse

%% =====================================================
%% OBSERVABILITY
%% =====================================================

Intent -.-> Tracing

Dense -.-> Tracing

Sparse -.-> Tracing

Graph -.-> Tracing

Planner -.-> Tracing

ToolExec -.-> Tracing

LLM -.-> Tracing

Confidence -.-> Tracing

Tracing --> Logs

Logs --> Latency

Latency --> Cost

Cost --> Tokens

%% =====================================================
%% EVALUATION
%% =====================================================

Logs -.-> Precision

Logs -.-> Recall

Logs -.-> Faithfulness

Logs -.-> Relevance

Logs -.-> LLMJudge

Precision --> Benchmark

Recall --> Benchmark

Faithfulness --> Benchmark

Relevance --> Benchmark

LLMJudge --> Benchmark

Benchmark --> RedTeam

%% =====================================================
%% FEEDBACK LOOPS
%% =====================================================

HumanReview --> Feedback

Benchmark --> Feedback

RedTeam --> Feedback

Feedback --> RetrievalTuning

Feedback --> PromptTuning

Feedback --> AgentTuning

Feedback --> GuardrailTuning

Feedback --> KnowledgeUpdates

Feedback --> FineTune

RetrievalTuning -.-> Reranker

PromptTuning -.-> PromptBuilder

AgentTuning -.-> Planner

GuardrailTuning -.-> PolicyCheck

KnowledgeUpdates -.-> VectorDB

KnowledgeUpdates -.-> Postgres

KnowledgeUpdates -.-> KG

FineTune -.-> LLM
```
### Query Understanding Subsystem
```mermaid
flowchart TD

UserQuery[User Query]

UserQuery --> Intent

Intent[Intent Classification]

Intent --> Complexity

Complexity{Complexity Level}

Complexity -->|Simple| Rewrite

Complexity -->|Medium| Expansion

Complexity -->|Complex| HyDE

Rewrite --> Canonical

Expansion --> Canonical

HyDE --> MultiQuery

MultiQuery --> Canonical

Canonical[Canonical Query]

Canonical --> Cache

Cache[Semantic Cache]
```

### Knowledge Ingestion Subsystem

```mermaid
flowchart TD

Source[Documents / PDFs / Images / Code]

Source --> Parser

Parser[Document Parser]

Parser --> Structure

Structure[Structure Extraction]

Structure --> Chunking

Chunking[Structure Aware Chunking]

Chunking --> Metadata

Metadata[Metadata Generation]

Metadata --> Summary

Metadata --> Keywords

Metadata --> Questions

Metadata --> Entities

Summary --> Embedding

Keywords --> Embedding

Questions --> Embedding

Entities --> Embedding

Embedding[Embedding Generation]

Embedding --> VectorDB[(Vector DB)]

Metadata --> Postgres[(Postgres)]

Entities --> GraphDB[(Knowledge Graph)]

Source --> ObjectStore[(Object Storage)]

```


### Query Understanding Subsystem

```mermaid
flowchart TD

    User([User Query])

    User --> InputPII[Input PII Detection]

    InputPII --> Intent[Intent Classification]

    Intent --> Complexity{Query Complexity}

    Complexity -->|Simple| Rewrite[Query Rewriting]

    Complexity -->|Medium| Expansion[Query Expansion]

    Complexity -->|Complex| HyDE[HyDE Generation]

    Rewrite --> Canonical[Canonical Query]

    Expansion --> Canonical[Canonical Query]

    HyDE --> MultiQuery[Multi Query Generation]

    MultiQuery --> Canonical

    Canonical --> Cache{Semantic Cache?}

    Cache -->|Hit| Streaming[Streaming Response]

    Cache -->|Miss| Retrieval[Retrieval System]

```

### Hybrid Retrieval Subsystem
```mermaid
flowchart TD

Query[Canonical Query]

Query --> Dense

Query --> Sparse

Query --> Graph

Dense[Dense Retrieval]
Sparse[BM25 Retrieval]
Graph[Graph Retrieval]

VectorDB[(Vector DB)] --> Dense
Postgres[(Postgres)] --> Sparse
KG[(Knowledge Graph)] --> Graph

Dense --> Filter
Sparse --> Filter
Graph --> Filter

Filter[Metadata Filtering]

Filter --> Fusion

Fusion[Hybrid Fusion]

Fusion --> Reranker

Reranker[Cross Encoder Reranker]

Reranker --> Compression

Compression[Context Compression]

Compression --> Dedup

Dedup[Deduplication]

Dedup --> Results[Retrieved Context]

```

### Agentic Reasoning Subsystem

```mermaid
flowchart TD

Context[Retrieved Context]

Context --> Planner

Planner[Task Planner]

Planner --> Decompose

Decompose[Task Decomposition]

Decompose --> ToolSelect

ToolSelect[Tool Selection]

ToolSelect --> ToolExec

ToolExec[Tool Execution]

ToolExec --> ToolStatus

ToolStatus{Tool Success?}

ToolStatus -->|No| Planner

ToolStatus -->|Yes| NeedMore

NeedMore{Need More Evidence?}

NeedMore -->|Yes| Retrieval

NeedMore -->|No| Evidence

Retrieval[Retrieval Layer]

Evidence[Evidence Aggregation]

Evidence --> Output[Reasoning Output]
```

### Context Engineering Subsystem
```mermaid
flowchart TD

Evidence[Evidence]

Evidence --> ContextBuilder

ContextBuilder[Context Builder]

ContextBuilder --> Compression

Compression[Context Compression]

Compression --> Citation

Citation[Citation Builder]

Citation --> Prompt

Prompt[Prompt Builder]

Prompt --> FinalPrompt[Final Prompt]
```

### Generation & Validation Subsystem

```mermaid
flowchart TD

Prompt[Final Prompt]

Prompt --> LLM

LLM[Reasoning LLM]

LLM --> Structured

Structured[Structured Output]

Structured --> Guardrail

Guardrail[Output Guardrails]

Guardrail --> PII

PII[PII Check]

PII --> Policy

Policy[Policy Check]

Policy --> Safety

Safety[Safety Validation]

Safety --> Grounding

Grounding[Grounding Verification]

Grounding --> Hallucination

Hallucination[Hallucination Detection]

Hallucination --> Consistency

Consistency[Consistency Check]

Consistency --> Confidence

Confidence[Confidence Score]
```

### Human Review Subsystem
```mermaid
flowchart TD

Confidence[Confidence Score]

Confidence --> Decision

Decision{Confidence OK?}

Decision -->|High| Cache

Decision -->|Low| Human

Human[Human Review Queue]

Human --> Approve

Approve[Approved Response]

Approve --> Cache

Cache[Response Cache]

Cache --> Stream

Stream[Streaming Layer]

Stream --> User[Final Response]
```

### Observability Subsystem
```mermaid
flowchart TD

Tracing[Distributed Tracing]

Tracing --> Logs

Logs[Centralized Logs]

Logs --> Latency

Latency[Latency Metrics]

Latency --> Cost

Cost[Cost Monitoring]

Cost --> Tokens

Tokens[Token Usage Analytics]

Tokens --> Dashboard

Dashboard[Monitoring Dashboard]
```

### Evaluation Subsystem
```mermaid
flowchart TD

Logs[Production Logs]

Logs --> Precision

Logs --> Recall

Logs --> Faithfulness

Logs --> Relevance

Logs --> LLMJudge

Precision --> Benchmark

Recall --> Benchmark

Faithfulness --> Benchmark

Relevance --> Benchmark

LLMJudge --> Benchmark

Benchmark[Benchmark Suite]

Benchmark --> RedTeam

RedTeam[Red Team Testing]

RedTeam --> Report

Report[Evaluation Report]
```

### Continuous Improvement Subsystem
```mermaid
flowchart TD

HumanReview[Human Review Feedback]

Evaluation[Evaluation Results]

RedTeam[Red Team Findings]

HumanReview --> Feedback

Evaluation --> Feedback

RedTeam --> Feedback

Feedback[Feedback Store]

Feedback --> Retrieval

Feedback --> Prompt

Feedback --> Agent

Feedback --> Guardrails

Feedback --> Knowledge

Feedback --> FineTune

Retrieval[Retrieval Tuning]

Prompt[Prompt Optimization]

Agent[Agent Optimization]

Guardrails[Guardrail Updates]

Knowledge[Knowledge Updates]

FineTune[Fine Tuning Dataset]
```

### System Life

```mermaid
flowchart TD

%% STAGE 1

subgraph S1["Stage 1 - Data Foundation"]
    A1[Identify Data Sources]
    A2[Document Parsing]
    A3[Structure Extraction]
    A4[Table Preservation]
    A5[Metadata Generation]
    A6[Version Tracking]
end

A1 --> A2 --> A3 --> A4 --> A5 --> A6

%% STAGE 2

subgraph S2["Stage 2 - Knowledge Preparation"]
    B1[Structure Aware Chunking]
    B2[Generate Summaries]
    B3[Extract Keywords]
    B4[Generate Hypothetical Questions]
    B5[Entity Extraction]
    B6[Embedding Generation]
end

B1 --> B2 --> B3 --> B4 --> B5 --> B6

%% STAGE 3

subgraph S3["Stage 3 - Storage Layer"]
    C1[Vector Database]
    C2[Relational Database]
    C3[Knowledge Graph]
    C4[Object Storage]
end

C1 --> C2 --> C3 --> C4

%% STAGE 4

subgraph S4["Stage 4 - Retrieval Layer"]
    D1[Semantic Search]
    D2[Keyword Search]
    D3[Metadata Filtering]
    D4[Graph Retrieval]
    D5[Hybrid Fusion]
    D6[Reranking]
    D7[Context Compression]
end

D1 --> D2 --> D3 --> D4 --> D5 --> D6 --> D7

%% STAGE 5

subgraph S5["Stage 5 - Query Intelligence"]
    E1[Intent Classification]
    E2[Query Rewriting]
    E3[Query Expansion]
    E4[Multi Query Retrieval]
    E5[Route Selection]
end

E1 --> E2 --> E3 --> E4 --> E5

%% STAGE 6

subgraph S6["Stage 6 - Agentic Reasoning"]
    F1[Task Planning]
    F2[Tool Selection]
    F3[Agent Coordination]
    F4[External Tool Execution]
    F5[Evidence Collection]
end

F1 --> F2 --> F3 --> F4 --> F5

%% STAGE 7

subgraph S7["Stage 7 - Response Generation"]
    G1[Context Assembly]
    G2[Citation Generation]
    G3[Prompt Construction]
    G4[LLM Generation]
end

G1 --> G2 --> G3 --> G4

%% STAGE 8

subgraph S8["Stage 8 - Validation"]
    H1[Grounding Check]
    H2[Hallucination Detection]
    H3[Safety Validation]
    H4[Policy Compliance]
    H5[Confidence Scoring]
end

H1 --> H2 --> H3 --> H4 --> H5

%% STAGE 9

subgraph S9["Stage 9 - Human Review"]
    I1[Human Approval Queue]
    I2[Escalation Workflow]
end

I1 --> I2

%% STAGE 10

subgraph S10["Stage 10 - Production Operations"]
    J1[Observability]
    J2[Logging]
    J3[Tracing]
    J4[Latency Monitoring]
    J5[Cost Tracking]
    J6[Caching]
end

J1 --> J2 --> J3 --> J4 --> J5 --> J6

%% STAGE 11

subgraph S11["Stage 11 - Evaluation"]
    K1[Precision]
    K2[Recall]
    K3[Faithfulness]
    K4[Answer Relevance]
    K5[Benchmark Testing]
end

K1 --> K2 --> K3 --> K4 --> K5

%% STAGE 12

subgraph S12["Stage 12 - Security & Stress Testing"]
    L1[Prompt Injection Tests]
    L2[Adversarial Testing]
    L3[Access Control Validation]
    L4[PII Protection]
    L5[Red Team Exercises]
end

L1 --> L2 --> L3 --> L4 --> L5

%% MAIN FLOW

S1 --> S2
S2 --> S3
S3 --> S4
S4 --> S5
S5 --> S6
S6 --> S7
S7 --> S8
S8 --> S9
S9 --> S10
S10 --> S11
S11 --> S12

```