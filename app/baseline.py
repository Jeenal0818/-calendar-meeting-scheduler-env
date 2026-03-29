from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .env import CalendarMeetingEnv
from .grader import grade
from .models import CreateMeetingAction, EnvironmentState, Event, MeetingRequest
from .tasks import TASKS


def _parse_hhmm(s: str) -> Tuple[int, int]:
    hh, mm = s.split(":")
    return int(hh), int(mm)


def _within_work_hours(state: EnvironmentState, user_id: str, start_utc: datetime, end_utc: datetime) -> bool:
    u = next(x for x in state.users if x.user_id == user_id)
    tz = ZoneInfo(u.timezone)
    s = start_utc.astimezone(tz)
    e = end_utc.astimezone(tz)
    if s.date() != e.date():
        return False
    wd = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][s.date().weekday()]
    window = u.work_hours[wd]
    ws_h, ws_m = _parse_hhmm(window.start)
    we_h, we_m = _parse_hhmm(window.end)
    ws = datetime(s.year, s.month, s.day, ws_h, ws_m, tzinfo=tz)
    we = datetime(s.year, s.month, s.day, we_h, we_m, tzinfo=tz)
    return (s >= ws) and (e <= we)


def _event_users(e: Event) -> set[str]:
    return set(e.attendees) | {e.owner_id}


def _conflicts(state: EnvironmentState, candidate: Event) -> bool:
    cand_users = _event_users(candidate)
    for e in state.events:
        if not (cand_users & _event_users(e)):
            continue
        if candidate.start < e.end and e.start < candidate.end:
            return True
    return False


def _daily_load_hours(state: EnvironmentState, user_id: str, local_day) -> float:
    u = next(x for x in state.users if x.user_id == user_id)
    tz = ZoneInfo(u.timezone)
    total = 0.0
    for e in state.events:
        if user_id not in _event_users(e):
            continue
        s = e.start.astimezone(tz)
        if s.date() != local_day:
            continue
        total += max(0.0, (e.end - e.start).total_seconds() / 3600.0)
    return total


def _would_exceed_caps(state: EnvironmentState, attendees: List[str], start_utc: datetime, end_utc: datetime) -> bool:
    for uid in attendees:
        u = next(x for x in state.users if x.user_id == uid)
        tz = ZoneInfo(u.timezone)
        d = start_utc.astimezone(tz).date()
        current = _daily_load_hours(state, uid, d)
        added = (end_utc - start_utc).total_seconds() / 3600.0
        if current + added > u.preferences.daily_meeting_cap_hours + 1e-6:
            return True
    return False


def _undesirable_penalty(state: EnvironmentState, user_id: str, start_utc: datetime) -> float:
    u = next(x for x in state.users if x.user_id == user_id)
    tz = ZoneInfo(u.timezone)
    s = start_utc.astimezone(tz)
    hhmm = f"{s.hour:02d}:{s.minute:02d}"
    soft_earliest = u.preferences.preferred_earliest_local
    soft_latest = u.preferences.preferred_latest_local

    def lt(a: str, b: str) -> bool:
        return _parse_hhmm(a) < _parse_hhmm(b)

    if lt(hhmm, "07:00") or lt("21:00", hhmm):
        return 3.0
    if lt(hhmm, soft_earliest) or lt(soft_latest, hhmm):
        return 1.0
    return 0.0


def _candidate_objective(task_id: str, state: EnvironmentState, req: MeetingRequest, start_utc: datetime) -> float:
    fairness = 0.0
    if task_id in {"calendar_team_fairness", "calendar_multi_timezone_robust"}:
        for uid in req.attendees:
            fairness += _undesirable_penalty(state, uid, start_utc)
    deadline_bias = (req.deadline.toordinal() - start_utc.date().toordinal()) * 0.02
    return fairness + max(0.0, deadline_bias)


def _find_slot(task_id: str, state: EnvironmentState, req: MeetingRequest) -> Optional[datetime]:
    horizon_start = state.meta.horizon_start
    horizon_end_excl = horizon_start.toordinal() + state.meta.horizon_days
    latest_day = min(req.deadline.toordinal(), horizon_end_excl - 1)

    best: Optional[datetime] = None
    best_obj = 1e18

    for day_ord in range(horizon_start.toordinal(), latest_day + 1):
        d = datetime.fromordinal(day_ord).date()
        for minutes in range(6 * 60, 20 * 60, 15):
            start_utc = datetime(d.year, d.month, d.day, 0, 0, tzinfo=ZoneInfo("UTC")) + timedelta(minutes=minutes)
            end_utc = start_utc + timedelta(minutes=req.duration_minutes)
            if end_utc.date().toordinal() != start_utc.date().toordinal():
                continue
            ok = True
            for uid in req.attendees:
                if not _within_work_hours(state, uid, start_utc, end_utc):
                    ok = False
                    break
            if not ok:
                continue
            if _would_exceed_caps(state, req.attendees, start_utc, end_utc):
                continue
            cand = Event(
                event_id="cand",
                title=req.title_hint,
                owner_id=req.organizer_id,
                attendees=req.attendees,
                start=start_utc,
                end=end_utc,
                is_virtual=True,
                location=None,
                is_mandatory=False,
                priority=req.priority,
                source="agent",
                linked_request_id=req.request_id,
            )
            if _conflicts(state, cand):
                continue
            obj = _candidate_objective(task_id, state, req, start_utc)
            if obj < best_obj - 1e-9:
                best_obj = obj
                best = start_utc
    return best


def run_baseline(task_id: str, seed: int = 0) -> float:
    env = CalendarMeetingEnv()
    st = env.reset(task_id, seed=seed)

    def prio_key(r: MeetingRequest):
        p = 2 if r.priority.value == "high" else (1 if r.priority.value == "medium" else 0)
        return (r.deadline, -p, r.request_id)

    for req in sorted(st.meeting_requests, key=prio_key):
        if any(e.linked_request_id == req.request_id for e in st.events):
            continue
        slot = _find_slot(task_id, st, req)
        if slot is None:
            continue
        st, _, _ = env.step(task_id, CreateMeetingAction(request_id=req.request_id, start=slot))

    return float(grade(task_id, st))


def run_baseline_for_all_tasks(seed: int = 0) -> Dict[str, float]:
    return {tid: run_baseline(tid, seed=seed) for tid in TASKS.keys()}


def main() -> None:
    print(json.dumps(run_baseline_for_all_tasks(seed=0), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
 
