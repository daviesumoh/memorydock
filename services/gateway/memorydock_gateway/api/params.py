from __future__ import annotations

from typing import Annotated

from fastapi import Query
from memorydock_core.paging import DEFAULT_LIMIT, MAX_LIMIT

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Page size")]
Cursor = Annotated[str | None, Query(max_length=512, description="Opaque cursor from next_cursor")]
DEFAULT_PAGE = DEFAULT_LIMIT
