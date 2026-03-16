from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

DATABASE_DIR = Path(__file__).parent.parent / "data"
DATABASE_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_DIR}/sim_tracker.db"
SYNC_DATABASE_URL = f"sqlite:///{DATABASE_DIR}/sim_tracker.db"

engine = create_async_engine(DATABASE_URL, echo=False)
sync_engine = create_engine(SYNC_DATABASE_URL, echo=False)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        from . import models
        await conn.run_sync(Base.metadata.create_all)
