from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import get_settings
from sqlalchemy.pool import NullPool

settings = get_settings()

if settings.use_in_memory:
    # Provide dummies so importers don't break, but DB won't be used.
    engine = None  # type: ignore
    SessionLocal = None  # type: ignore
    class DummyBase:  # minimal stand-in
        metadata = None
    Base = declarative_base()  # still allow model definitions if any code references
    async def get_db():  # type: ignore
        # Yield a no-op async context manager substitute
        class Dummy:
            async def __aenter__(self): return None
            async def __aexit__(self, exc_type, exc, tb): return False
        yield None
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        poolclass=NullPool if settings.database_url.startswith("sqlite") else None,
    )
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    Base = declarative_base()

    async def get_db():
        async with SessionLocal() as session:  # type: ignore
            yield session
