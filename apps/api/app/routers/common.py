from dataclasses import dataclass

from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session


@dataclass
class Page:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> Page:
    return Page(page, page_size)


def paginate(db: Session, stmt, page: Page, serialize) -> dict:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.offset(page.offset).limit(page.page_size)).all()
    return {"items": [serialize(r) for r in rows], "total": total, "page": page.page, "page_size": page.page_size}
