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
    GEMINI_API_KEY: str = ""
    COHERE_API_KEY: str = ""

    # Pydantic settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore" # ignore extra env variables
    )

# Instantiate settings
settings = Settings()
