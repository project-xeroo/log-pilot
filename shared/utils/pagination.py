from __future__ import annotations

import math
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Query

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate(query: Query, page: int = 1, page_size: int = 20) -> tuple[list, int]:
    """Return (items, total) for the given SQLAlchemy query with offset/limit."""
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total
