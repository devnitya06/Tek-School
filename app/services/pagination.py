from math import ceil
from fastapi import Query
from typing import Optional, Any, List, Dict


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        per_page: int = Query(10, ge=1, le=100),
    ):
        self.page = page
        self.per_page = per_page

    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    def limit(self) -> int:
        return self.per_page

    def format_response(self, data: List[Any], total_count: Optional[int] = None) -> Dict[str, Any]:
        total_count = total_count if total_count is not None else len(data)
        total_pages = ceil(total_count / self.per_page) if self.per_page else 1

        return {
            "page": self.page,
            "per_page": self.per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "items": data,
        }
