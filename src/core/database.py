from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from core.config import settings
from core.models import Base
from core.logger import info, error as log_error

# Construct the asyncpg database URI
DATABASE_URL = (
    f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

# Initialize the async database engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_size=50,
    max_overflow=100
)

# Create a session factory
async_session_maker = async_sessionmaker(
    engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection generator to yield active database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

async def init_db() -> bool:
    """
    Enables the pgvector extension and creates all tables.
    Returns True on success, False if connection fails.
    """
    try:
        async with engine.begin() as conn:
            # Enable pgvector extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Create all tables defined in models.py
            await conn.run_sync(Base.metadata.create_all)
        info("database", "Database initialized successfully with pgvector and tables.")
        return True
    except Exception as e:
        log_error("database",
            f"Failed to initialize database: {e}. "
            "Please ensure PostgreSQL is running with pgvector on the configured host/port."
        )
        raise e
