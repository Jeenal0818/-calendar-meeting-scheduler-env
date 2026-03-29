from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import random


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 7860


@dataclass(frozen=True)
class Horizon:
    start_date: date
    days: int

    @property
    def end_date_exclusive(self) -> date:
        return self.start_date + timedelta(days=self.days)


def stable_int_seed(task_id: str, seed: int | None) -> int:
    base = f"{task_id}::{seed if seed is not None else 'none'}"
    digest = hashlib.sha256(base.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False) % (2**31 - 1)


def rng_for(task_id: str, seed: int | None) -> random.Random:
    return random.Random(stable_int_seed(task_id, seed))


def ref_horizon(task_id: str, seed: int | None, days: int) -> Horizon:
    r = rng_for(task_id, seed)
    start = date(2026, 3, 30) + timedelta(days=r.randint(0, 3))
    return Horizon(start_date=start, days=days)


def dt_local(d: date, hh: int, mm: int, tz: str) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=ZoneInfo(tz))


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
