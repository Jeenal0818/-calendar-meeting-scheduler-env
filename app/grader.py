from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Tuple
from zoneinfo import ZoneInfo
import math

from .config import WEEKDAYS
from .models import EnvironmentState, Event, EventPriority, MeetingRequest


@dataclass(frozen=True)
class Metrics:
    coverage: float
    conflict_free: float
    working_hours_ok: float
    daily_caps_ok: float
    fairness: float
    stability: float


def _parse_hhmm(s: str) -> Tuple[int, int]:
    hh, mm = s.split(":")
    return int(hh), int(mm)


def _weekday_key(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def _event_users(e: Event) -> List[str]:
    users = set(e.attendees)
    users.add(e.owner_id)
    return sorted(users)


def _events_for_user(events: Iterable[Event], user_id: str) -> List[Event]:
    out: List[Event] = []
    for e in events:
        if user_id in _event_users(e):
            out.append(e)
    return out


def _has_overlap(e1: Event, e2: Event) -> bool:
    return e1.start < e2.end and e2.start < e1.end


def conflict_free_ratio(state: EnvironmentState) -> float:
    user_ids = [u.user_id for u in state.users]
    ok = 0
    for uid in user_ids:
        evs = sorted(_events_for_user(state.events, uid), key=lambda e: (e.start, e.end, e.event_id))
        conflict = False
        for i in range(len(evs) - 1):
            if _has_overlap(evs[i], evs[i + 1]):
                conflict = True
                break
        if not conflict:
            ok += 1
    return ok / max(1, len(user_ids))


def _within_work_hours_for_user(state: EnvironmentState, user_id: str, start_utc: datetime, end_utc: datetime) -> bool:
    u = next(x for x in state.users if x.user_id == user_id)
    tz = ZoneInfo(u.timezone)
    s = start_utc.astimezone(tz)
    e = end_utc.astimezone(tz)
    if s.date() != e.date():
        return False
    wd = _weekday_key(s.date())
    window = u.work_hours[wd]
    ws_h, ws_m = _parse_hhmm(window.start)
    we_h, we_m = _parse_hhmm(window.end)
    ws = datetime(s.year, s.month, s.day, ws_h, ws_m, tzinfo=tz)
    we = datetime(s.year, s.month, s.day, we_h, we_m, tzinfo=tz)
    return (s >= ws) and (e <= we)


def working_hours_compliance(state: EnvironmentState) -> float:
    if not state.events:
        return 1.0
    ok = 0
    total = 0
    for e in state.events:
        users = _event_users(e)
        for uid in users:
            total += 1
            if _within_work_hours_for_user(state, uid, e.start, e.end):
                ok += 1
    return ok / max(1, total)


def _daily_load_hours(state: EnvironmentState, user_id: str, local_day: date) -> float:
    u = next(x for x in state.users if x.user_id == user_id)
    tz = ZoneInfo(u.timezone)
    total = 0.0
    for e in _events_for_user(state.events, user_id):
        s = e.start.astimezone(tz)
        if s.date() != local_day:
            continue
        total += max(0.0, (e.end - e.start).total_seconds() / 3600.0)
    return total


def daily_caps_compliance(state: EnvironmentState) -> float:
    user_ids = [u.user_id for u in state.users]
    if not state.events:
        return 1.0
    checks = 0
    ok = 0
    for u in state.users:
        tz = ZoneInfo(u.timezone)
        days = set()
        for e in _events_for_user(state.events, u.user_id):
            days.add(e.start.astimezone(tz).date())
        for d in days:
            checks += 1
            load = _daily_load_hours(state, u.user_id, d)
            if load <= u.preferences.daily_meeting_cap_hours + 1e-6:
                ok += 1
    return ok / max(1, checks)


def _scheduled_request_ids(state: EnvironmentState) -> Dict[str, Event]:
    m: Dict[str, Event] = {}
    for e in state.events:
        if e.linked_request_id:
            m[e.linked_request_id] = e
    return m


def coverage_ratio(state: EnvironmentState) -> float:
    if not state.meeting_requests:
        return 1.0
    scheduled = _scheduled_request_ids(state)
    ok = 0
    for req in state.meeting_requests:
        e = scheduled.get(req.request_id)
        if e is None:
            continue
        minutes = int(round((e.end - e.start).total_seconds() / 60.0))
        if minutes != req.duration_minutes:
            continue
        if e.start.date() > req.deadline:
            continue
        ok += 1
    return ok / max(1, len(state.meeting_requests))


def _undesirable_local_time_penalty(state: EnvironmentState, user_id: str, e: Event) -> float:
    u = next(x for x in state.users if x.user_id == user_id)
    tz = ZoneInfo(u.timezone)
    s = e.start.astimezone(tz)
    hhmm = f"{s.hour:02d}:{s.minute:02d}"
    soft_earliest = u.preferences.preferred_earliest_local
    soft_latest = u.preferences.preferred_latest_local
    hard_earliest = "07:00"
    hard_latest = "21:00"

    def lt(a: str, b: str) -> bool:
        return _parse_hhmm(a) < _parse_hhmm(b)

    if lt(hhmm, hard_earliest) or lt(hard_latest, hhmm):
        return 1.0
    if lt(hhmm, soft_earliest) or lt(soft_latest, hhmm):
        return 0.4
    return 0.0


def fairness_score(state: EnvironmentState) -> float:
    if not state.events:
        return 1.0
    per_user: Dict[str, float] = {u.user_id: 0.0 for u in state.users}
    counts: Dict[str, int] = {u.user_id: 0 for u in state.users}
    for e in state.events:
        if e.linked_request_id is None:
            continue
        for uid in _event_users(e):
            per_user[uid] += _undesirable_local_time_penalty(state, uid, e)
            counts[uid] += 1
    vals = []
    for uid in per_user:
        if counts[uid] == 0:
            continue
        vals.append(per_user[uid] / counts[uid])
    if not vals:
        return 1.0
    mu = sum(vals) / len(vals)
    var = sum((x - mu) ** 2 for x in vals) / max(1, len(vals))
    sd = math.sqrt(var)
    return float(max(0.0, min(1.0, 1.0 - sd / 0.7)))


def stability_score(state: EnvironmentState) -> float:
    anchors = state.meta.seeded_mandatory_anchors
    if not anchors:
        return 1.0
    unchanged = 0
    for event_id, (s0, e0) in anchors.items():
        e = next((x for x in state.events if x.event_id == event_id), None)
        if e is None:
            continue
        if e.start == s0 and e.end == e0:
            unchanged += 1
    return unchanged / max(1, len(anchors))


def compute_metrics(task_id: str, state: EnvironmentState) -> Metrics:
    cov = coverage_ratio(state)
    conf = conflict_free_ratio(state)
    wh = working_hours_compliance(state)
    caps = daily_caps_compliance(state)
    fair = fairness_score(state) if task_id in {"calendar_team_fairness", "calendar_multi_timezone_robust"} else 1.0
    stab = stability_score(state) if task_id == "calendar_multi_timezone_robust" else 1.0
    return Metrics(
        coverage=cov,
        conflict_free=conf,
        working_hours_ok=wh,
        daily_caps_ok=caps,
        fairness=fair,
        stability=stab,
    )


def grade(task_id: str, state: EnvironmentState) -> float:
    m = compute_metrics(task_id, state)
    if task_id == "calendar_easy_1v1":
        score = 0.62 * m.coverage + 0.18 * m.working_hours_ok + 0.20 * m.conflict_free
    elif task_id == "calendar_team_fairness":
        score = (
            0.45 * m.coverage
            + 0.15 * m.working_hours_ok
            + 0.15 * m.conflict_free
            + 0.15 * m.daily_caps_ok
            + 0.10 * m.fairness
        )
    elif task_id == "calendar_multi_timezone_robust":
        score = (
            0.38 * m.coverage
            + 0.12 * m.working_hours_ok
            + 0.12 * m.conflict_free
            + 0.13 * m.daily_caps_ok
            + 0.15 * m.fairness
            + 0.10 * m.stability
        )
    else:
        score = 0.0

    return float(max(0.0, min(1.0, score)))
