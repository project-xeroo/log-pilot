from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from .settings import get_settings


def _get_engine():
    s = get_settings()
    return create_async_engine(
        s.database_url,
        pool_size=s.database_pool_size,
        max_overflow=s.database_max_overflow,
        echo=False,
    )


# Lazy singletons — engine created on first use, not at import time
_engine = None
_session_factory = None


def _engine_instance():
    global _engine
    if _engine is None:
        _engine = _get_engine()
    return _engine


def _session_factory_instance():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_engine_instance(), expire_on_commit=False)
    return _session_factory


# Expose as module-level names for compatibility with existing imports
class _LazyEngine:
    """Proxy that creates the engine on first attribute access."""
    def __getattr__(self, name):
        return getattr(_engine_instance(), name)

    def __call__(self, *args, **kwargs):
        return _engine_instance()(*args, **kwargs)


class _LazySessionLocal:
    """Proxy that creates the sessionmaker on first attribute access."""
    def __getattr__(self, name):
        return getattr(_session_factory_instance(), name)

    def __call__(self, *args, **kwargs):
        return _session_factory_instance()(*args, **kwargs)


engine = _LazyEngine()
AsyncSessionLocal = _LazySessionLocal()


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async DB session."""
    async with _session_factory_instance()() as session:
        yield session
