import json
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..database import get_db
from ..dependencies import BusinessContext, business_context
from ..domain import permissions as P
from ..domain.periods import KINDS, PeriodError, resolve
from ..models import DayClose
from ..schemas.business import DayCloseCreate
from ..services.analytics import BusinessAnalytics, business_date_period
from ..services.audit import audit
from ..services.report_export import report_csv

router = APIRouter(prefix="/business", tags=["Business analytics"])


def _period(kind: str, period: str | None, start: date | None, end: date | None):
    try:
        return resolve(period or BusinessAnalytics.DEFAULT_PERIOD[kind], start, end)
    except PeriodError as exc:
        raise AppError(422, "INVALID_PERIOD", str(exc)) from exc


def _report_kind(kind: str, ctx: BusinessContext) -> None:
    if kind not in P.REPORT_CAPABILITY:
        raise AppError(404, "NOT_FOUND", "Report not found")
    ctx.require(P.REPORT_CAPABILITY[kind])


@router.get("/dashboard")
def dashboard(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Role-aware: what needs attention, today's operations, and (owner) performance with comparisons."""
    return BusinessAnalytics(db, ctx.business).dashboard(ctx.user.role)


@router.get("/reports")
def reports(ctx: BusinessContext = Depends(business_context)):
    return {"reports": [{"kind": k, "default_period": BusinessAnalytics.DEFAULT_PERIOD[k]}
                        for k, cap in P.REPORT_CAPABILITY.items() if ctx.can(cap)],
            "periods": list(KINDS)}


@router.get("/reports/{kind}")
def report(kind: str, period: str | None = Query(None, max_length=20), start: date | None = None, end: date | None = None,
           ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    _report_kind(kind, ctx)
    return BusinessAnalytics(db, ctx.business).report(kind, _period(kind, period, start, end))


@router.get("/reports/{kind}/export.csv")
def report_export(kind: str, period: str | None = Query(None, max_length=20), start: date | None = None,
                  end: date | None = None, lang: str = Query("en", pattern="^(en|sw)$"),
                  ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    _report_kind(kind, ctx)
    p = _period(kind, period, start, end)
    data = BusinessAnalytics(db, ctx.business).report(kind, p)
    filename = f"launder-{kind}-{p.start_date.isoformat()}" + ("" if p.days == 1 else f"-to-{p.end_date.isoformat()}") + ".csv"
    # BOM so Excel opens Swahili text and the en dash correctly.
    return Response("﻿" + report_csv(data, lang), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/day-close", status_code=201)
def close_day(payload: DayCloseCreate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Operational confirmation of a business day. Records what was expected and counted; locks nothing."""
    ctx.require("reports.operational")
    analytics = BusinessAnalytics(db, ctx.business)
    period = business_date_period(payload.date, analytics.now)
    if period.start > analytics.now:
        raise AppError(422, "DAY_NOT_STARTED", "You can only close today or a past day")
    report_data = analytics.report("daily", period)
    view = report_data["day_close"]
    if view["closed"]:
        raise AppError(409, "DAY_ALREADY_CLOSED", "This day has already been closed")
    snapshot = {k: report_data[k] for k in ("summary", "day_book", "money", "payments", "sources")}
    record = DayClose(business_id=ctx.business.id, business_date=payload.date, expected_cash=view["expected_cash"],
                      counted_cash=payload.counted_cash, note=payload.note, closed_by=ctx.user.id,
                      snapshot_json=json.dumps(snapshot, default=str))
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "DAY_ALREADY_CLOSED", "This day has already been closed") from None
    audit(db, ctx.user.id, "DAY_CLOSED", "business", ctx.business.id, date=payload.date.isoformat(),
          expected_cash=record.expected_cash, counted_cash=record.counted_cash)
    db.commit()
    return analytics.day_close_view(period)


@router.get("/day-close")
def day_close_history(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("reports.operational")
    rows = db.scalars(select(DayClose).where(DayClose.business_id == ctx.business.id)
                      .order_by(DayClose.business_date.desc()).limit(31))
    return {"items": [{"date": r.business_date.isoformat(), "expected_cash": r.expected_cash, "counted_cash": r.counted_cash,
                       "variance": None if r.counted_cash is None else r.counted_cash - r.expected_cash,
                       "closed_at": r.closed_at} for r in rows]}
