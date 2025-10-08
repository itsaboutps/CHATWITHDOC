from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import get_settings
from sqlalchemy.pool import NullPool

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, future=True, poolclass=NullPool if settings.database_url.startswith("sqlite") else None)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session
