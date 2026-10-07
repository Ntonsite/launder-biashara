"""Reporting periods in the business's local time (Africa/Dar_es_Salaam, no DST) and their comparison periods.

Comparisons are like-for-like:
* a period still in progress is compared with the same elapsed length of the previous period
  (month-to-date vs the same days of last month; today so far vs last week's same weekday up to the same time);
* months compare with calendar months, days with the same weekday a week earlier (laundry demand is weekly),
  everything else with the period of the same length immediately before.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from .clock import LOCAL_TZ, now_utc

KINDS = ("today", "yesterday", "last_7_days", "this_week", "last_week", "this_month", "last_month", "custom")
MAX_CUSTOM_DAYS = 366


class PeriodError(ValueError):
    pass


@dataclass(frozen=True)
class Period:
    kind: str
    start_date: date  # inclusive, local
    end_date: date  # inclusive, local
    start: datetime  # UTC, inclusive
    end: datetime  # UTC, exclusive: the natural end of the period
    until: datetime  # UTC: min(end, now) — data cannot exist beyond now
    prev_start: datetime
    prev_until: datetime
    compare_to: str  # previous_day_same_weekday | previous_week | previous_month | previous_period

    @property
    def in_progress(self) -> bool:
        return self.until < self.end

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def local_dates(self) -> list[date]:
        return [self.start_date + timedelta(days=i) for i in range(self.days)]

    def out(self) -> dict:
        return {"kind": self.kind, "start_date": self.start_date.isoformat(), "end_date": self.end_date.isoformat(),
                "in_progress": self.in_progress, "compare_to": self.compare_to,
                "previous_start": _local(self.prev_start).isoformat(), "previous_until": _local(self.prev_until).isoformat()}


def _local(value: datetime) -> datetime:
    return value.astimezone(LOCAL_TZ)


def local_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, LOCAL_TZ).astimezone(UTC)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def resolve(kind: str = "today", start: date | None = None, end: date | None = None, now: datetime | None = None) -> Period:
    now = (now or now_utc()).astimezone(UTC)
    today = _local(now).date()
    if kind not in KINDS:
        raise PeriodError(f"Unknown period {kind}")
    compare = "previous_period"
    if kind == "today":
        first = last = today
        compare = "previous_day_same_weekday"
    elif kind == "yesterday":
        first = last = today - timedelta(days=1)
        compare = "previous_day_same_weekday"
    elif kind == "last_7_days":
        first, last = today - timedelta(days=6), today
    elif kind == "this_week":
        first = today - timedelta(days=today.weekday())
        last = first + timedelta(days=6)
        compare = "previous_week"
    elif kind == "last_week":
        first = today - timedelta(days=today.weekday() + 7)
        last = first + timedelta(days=6)
        compare = "previous_week"
    elif kind == "this_month":
        first = _month_start(today)
        last = _add_months(first, 1) - timedelta(days=1)
        compare = "previous_month"
    elif kind == "last_month":
        first = _add_months(_month_start(today), -1)
        last = _month_start(today) - timedelta(days=1)
        compare = "previous_month"
    else:
        if not start or not end:
            raise PeriodError("Custom periods need a start and an end date")
        if end < start:
            raise PeriodError("The end date is before the start date")
        if (end - start).days + 1 > MAX_CUSTOM_DAYS:
            raise PeriodError(f"Choose a period of at most {MAX_CUSTOM_DAYS} days")
        first, last = start, end

    period_start, period_end = local_midnight(first), local_midnight(last + timedelta(days=1))
    until = max(min(period_end, now), period_start)
    elapsed = until - period_start

    if compare == "previous_month":
        prev_first = _add_months(first, -1)
        prev_start = local_midnight(prev_first)
        prev_natural_end = local_midnight(first)
        prev_until = min(prev_start + elapsed, prev_natural_end) if until < period_end else prev_natural_end
    else:
        shift = timedelta(days=7) if compare in ("previous_day_same_weekday", "previous_week") else period_end - period_start
        prev_start = period_start - shift
        prev_until = prev_start + elapsed
    return Period(kind, first, last, period_start, period_end, until, prev_start, prev_until, compare)
