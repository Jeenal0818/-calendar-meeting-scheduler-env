from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

from .grader import Metrics, compute_metrics
from .models import (
    Action,
    CancelEventAction,
    CreateMeetingAction,
    EnvironmentState,
    Event,
    EventPriority,
    MoveEventAction,
    NoOpAction,
)
from .tasks import build_state


def _event_users(e: Event) -> set[str]:
    return set(e.attendees) | {e.owner_id}


def _new_event_id(state: EnvironmentState) -> str:
    taken = {e.event_id for e in state.events}
    i = len(taken) + 1
    while True:
        cand = f"ev_{i:03d}"
        if cand not in taken:
            return cand
        i += 1


def _has_overlap(a: Event, b: Event) -> bool:
    return a.start < b.end and b.start < a.end


def _introduces_conflict(state: EnvironmentState, candidate: Event, ignore_event_id: Optional[str] = None) -> bool:
    cand_users = _event_users(candidate)
    for e in state.events:
        if ignore_event_id and e.event_id == ignore_event_id:
            continue
        if not (cand_users & _event_users(e)):
            continue
        if _has_overlap(candidate, e):
            return True
    return False


def _find_request(state: EnvironmentState, request_id: str):
    for req in state.meeting_requests:
        if req.request_id == request_id:
            return req
    return None


def _already_scheduled(state: EnvironmentState, request_id: str) -> bool:
    return any(e.linked_request_id == request_id for e in state.events)


def _in_horizon(state: EnvironmentState, start_utc: datetime, end_utc: datetime) -> bool:
    d0 = state.meta.horizon_start
    d1 = state.meta.horizon_start.toordinal() + state.meta.horizon_days
    s_ord = start_utc.date().toordinal()
    e_ord = end_utc.date().toordinal()
    return (d0.toordinal() <= s_ord < d1) and (d0.toordinal() <= e_ord < d1)


def _reward_from_delta(old: Metrics, new: Metrics, task_id: str) -> float:
    cov = new.coverage - old.coverage
    conf = new.conflict_free - old.conflict_free
    wh = new.working_hours_ok - old.working_hours_ok
    caps = new.daily_caps_ok - old.daily_caps_ok
    fair = new.fairness - old.fairness
    stab = new.stability - old.stability

    w_fair = 0.35 if task_id in {"calendar_team_fairness", "calendar_multi_timezone_robust"} else 0.0
    w_caps = 0.30 if task_id in {"calendar_team_fairness", "calendar_multi_timezone_robust"} else 0.10
    w_stab = 0.35 if task_id == "calendar_multi_timezone_robust" else 0.0

    reward = (
        1.4 * cov
        + 0.55 * conf
        + 0.45 * wh
        + w_caps * caps
        + w_fair * fair
        + w_stab * stab
    )

    if conf < 0:
        reward -= 0.2 * abs(conf)
    if wh < 0:
        reward -= 0.15 * abs(wh)
    if caps < 0:
        reward -= 0.10 * abs(caps)

    return float(reward)


def _done_condition(task_id: str, m: Metrics, step_count: int) -> bool:
    if step_count >= 60:
        return True
    if m.coverage < 0.999:
        return False
    if m.conflict_free < 0.999:
        return False
    if m.working_hours_ok < 0.995:
        return False
    if task_id in {"calendar_team_fairness", "calendar_multi_timezone_robust"} and m.daily_caps_ok < 0.995:
        return False
    if task_id in {"calendar_team_fairness", "calendar_multi_timezone_robust"} and m.fairness < 0.55:
        return False
    if task_id == "calendar_multi_timezone_robust" and m.stability < 0.75:
        return False
    return True


@dataclass
class CalendarMeetingEnv:
    state: Optional[EnvironmentState] = None
    last_metrics: Optional[Metrics] = None

    def reset(self, task_id: str, seed: int | None) -> EnvironmentState:
        st = build_state(task_id, seed)
        self.state = st
        self.last_metrics = compute_metrics(task_id, st)
        return st

    def step(self, task_id: str, action: Action) -> Tuple[EnvironmentState, float, bool]:
        if self.state is None or self.state.meta.task_id != task_id:
            self.reset(task_id, seed=None)

        assert self.state is not None
        st = self.state
        old = self.last_metrics or compute_metrics(task_id, st)

        st.meta.step_count += 1
        st.meta.last_action = action.model_dump()

        if isinstance(action, NoOpAction):
            pass

        elif isinstance(action, CreateMeetingAction):
            req = _find_request(st, action.request_id)
            if req is None:
                pass
            elif _already_scheduled(st, req.request_id):
                pass
            else:
                start = action.start
                end = start + timedelta(minutes=req.duration_minutes)
                if start.date() > req.deadline:
                    pass
                elif not _in_horizon(st, start, end):
                    pass
                else:
                    new_event = Event(
                        event_id=_new_event_id(st),
                        title=action.title or req.title_hint,
                        owner_id=req.organizer_id,
                        attendees=list(dict.fromkeys(req.attendees)),
                        start=start,
                        end=end,
                        is_virtual=action.is_virtual,
                        location=action.location,
                        is_mandatory=req.priority == EventPriority.high and req.meeting_type.value in {"standup", "sync"},
                        priority=req.priority,
                        source="agent",
                        linked_request_id=req.request_id,
                    )
                    if not _introduces_conflict(st, new_event):
                        st.events.append(new_event)

        elif isinstance(action, MoveEventAction):
            e = next((x for x in st.events if x.event_id == action.event_id), None)
            if e is None:
                pass
            elif e.is_mandatory and e.priority == EventPriority.high and e.source == "seeded":
                pass
            elif action.new_end <= action.new_start:
                pass
            elif not _in_horizon(st, action.new_start, action.new_end):
                pass
            else:
                candidate = e.model_copy()
                candidate.start = action.new_start
                candidate.end = action.new_end
                if not _introduces_conflict(st, candidate, ignore_event_id=e.event_id):
                    e.start = action.new_start
                    e.end = action.new_end

        elif isinstance(action, CancelEventAction):
            e = next((x for x in st.events if x.event_id == action.event_id), None)
            if e is None:
                pass
            elif e.is_mandatory:
                pass
            else:
                st.events = [x for x in st.events if x.event_id != action.event_id]

        new = compute_metrics(task_id, st)
        reward = _reward_from_delta(old, new, task_id)
        done = _done_condition(task_id, new, st.meta.step_count)

        self.state = st
        self.last_metrics = new
        return st, reward, done


ACTIVE_ENV = CalendarMeetingEnv()
