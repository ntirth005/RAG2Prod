from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG2Prod"
    API_V1_STR: str = "/api/v1"
    
    # Database Configurations (Stage 2)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "rag2prod"
    
    # Vector Database (Stage 2)
    VECTOR_DB_HOST: str = "localhost"
    VECTOR_DB_PORT: int = 8000

    # Graph Database (Stage 18)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j"
    
    # LLM Settings (Stage 5)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL_NAME: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL_NAME: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    
    GEMINI_API_KEY: str = ""
    COHERE_API_KEY: str = ""
    
    # Generation Parameters (Stage 5)
    LLM_DEFAULT_PROVIDER: str = "deepseek"
    LLM_MAX_OUTPUT_TOKENS: int = 1024
    LLM_TEMPERATURE: float = 0.3
    MAX_CONTEXT_TOKENS: int = 4000

    # Ingestion & Embedding Configurations (Stage 1)
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    DEFAULT_CHUNK_SIZE: int = 500
    DEFAULT_CHUNK_OVERLAP: int = 50
    OCR_CACHE_DIR: str = ".cache/ocr"
    OBJECT_STORAGE_LOCAL_DIR: str = ".storage"

    # Hybrid Retrieval & Reranking Configurations (Stage 7)
    ENABLE_HYBRID_SEARCH: bool = True
    ENABLE_RERANKING: bool = True
    RERANKER_MODEL_NAME: str = "BAAI/bge-reranker-base"
    RRF_K_CONSTANT: int = 60
    HYBRID_TOP_K_CANDIDATES: int = 20

    # Pydantic settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore" # ignore extra env variables
    )

# Instantiate settings
settings = Settings()
