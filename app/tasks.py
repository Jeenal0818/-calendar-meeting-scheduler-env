from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Dict, List, Tuple

from .config import WEEKDAYS, Horizon, dt_local, rng_for, ref_horizon, to_utc
from .models import (
    DailyWindow,
    EnvironmentState,
    EnvMeta,
    Event,
    EventPriority,
    MeetingRequest,
    MeetingType,
    User,
    UserPreferences,
)


@dataclass(frozen=True)
class TaskDef:
    task_id: str
    name: str
    description: str
    difficulty: str
    horizon_days: int
    build: Callable[[int | None], EnvironmentState]


def _weekday_key(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def _mk_work_hours(start: str, end: str) -> Dict[str, DailyWindow]:
    return {wd: DailyWindow(start=start, end=end) for wd in WEEKDAYS}


def _u(user_id: str, name: str, tz: str, wh: Tuple[str, str], cap: float, prefer_morning: bool | None) -> User:
    prefs = UserPreferences(
        daily_meeting_cap_hours=cap,
        prefer_morning=prefer_morning,
        preferred_earliest_local="09:00",
        preferred_latest_local="17:00",
    )
    return User(
        user_id=user_id,
        name=name,
        timezone=tz,
        work_hours=_mk_work_hours(wh[0], wh[1]),
        preferences=prefs,
    )


def _new_id(prefix: str, n: int) -> str:
    return f"{prefix}_{n:03d}"


def _seeded_event(
    event_id: str,
    title: str,
    owner_id: str,
    attendees: List[str],
    start_local,
    end_local,
    *,
    is_virtual: bool,
    location: str | None,
    is_mandatory: bool,
    priority: EventPriority,
) -> Event:
    return Event(
        event_id=event_id,
        title=title,
        owner_id=owner_id,
        attendees=attendees,
        start=to_utc(start_local),
        end=to_utc(end_local),
        is_virtual=is_virtual,
        location=location,
        is_mandatory=is_mandatory,
        priority=priority,
        source="seeded",
    )


def build_task1(seed: int | None) -> EnvironmentState:
    task_id = "calendar_easy_1v1"
    r = rng_for(task_id, seed)
    hz = ref_horizon(task_id, seed, days=7)

    users = [
        _u("u_alex", "Alex Chen", "Europe/Berlin", ("10:00", "18:00"), cap=2.5, prefer_morning=True),
        _u("u_blair", "Blair Novak", "Europe/Berlin", ("10:00", "18:00"), cap=2.5, prefer_morning=None),
        _u("u_casey", "Casey Rivera", "Europe/Berlin", ("10:00", "18:00"), cap=2.5, prefer_morning=False),
    ]
    org = users[0].user_id
    others = [users[1].user_id, users[2].user_id]

    events: List[Event] = []
    d0 = hz.start_date
    for i in range(3):
        d = d0 + timedelta(days=i)
        if _weekday_key(d) in {"sat", "sun"}:
            continue
        owner = r.choice(users).user_id
        start_h = r.choice([11, 14, 16])
        ev = _seeded_event(
            _new_id("ev", len(events) + 1),
            "Focus block",
            owner,
            [owner],
            dt_local(d, start_h, 0, "Europe/Berlin"),
            dt_local(d, start_h + 1, 0, "Europe/Berlin"),
            is_virtual=False,
            location="Desk",
            is_mandatory=False,
            priority=EventPriority.low,
        )
        events.append(ev)

    reqs: List[MeetingRequest] = []
    for j, attendee in enumerate(r.sample(others, k=2 if r.random() < 0.7 else 1), start=1):
        deadline = hz.start_date + timedelta(days=5)
        reqs.append(
            MeetingRequest(
                request_id=_new_id("req", j),
                organizer_id=org,
                attendees=[org, attendee],
                duration_minutes=30,
                deadline=deadline,
                meeting_type=MeetingType.one_on_one,
                priority=EventPriority.medium,
                title_hint="1:1",
            )
        )

    meta = EnvMeta(
        task_id=task_id,
        seed=0 if seed is None else seed,
        horizon_start=hz.start_date,
        horizon_days=hz.days,
    )
    return EnvironmentState(meta=meta, users=users, events=events, meeting_requests=reqs)


def build_task2(seed: int | None) -> EnvironmentState:
    task_id = "calendar_team_fairness"
    r = rng_for(task_id, seed)
    hz = ref_horizon(task_id, seed, days=10)

    users = [
        _u("u_dana", "Dana Singh", "Europe/Berlin", ("09:30", "17:30"), cap=3.0, prefer_morning=True),
        _u("u_eli", "Eli Park", "Europe/Berlin", ("09:30", "17:30"), cap=3.0, prefer_morning=None),
        _u("u_finn", "Finn Ito", "Asia/Kolkata", ("10:00", "18:00"), cap=3.0, prefer_morning=False),
        _u("u_gale", "Gale Watson", "Asia/Kolkata", ("10:00", "18:00"), cap=3.0, prefer_morning=True),
        _u("u_haru", "Haru Kim", "Asia/Kolkata", ("10:00", "18:00"), cap=3.0, prefer_morning=None),
    ]
    team = [u.user_id for u in users]
    organizer = users[0].user_id

    events: List[Event] = []
    for k in range(12):
        d = hz.start_date + timedelta(days=r.randint(0, 6))
        if _weekday_key(d) in {"sat", "sun"}:
            continue
        u = r.choice(users)
        start_h = r.choice([10, 11, 14, 15, 16])
        dur_h = r.choice([1, 1, 2])
        events.append(
            _seeded_event(
                _new_id("ev", len(events) + 1),
                r.choice(["Customer call", "Interview", "Deep work", "Project review"]),
                u.user_id,
                [u.user_id],
                dt_local(d, start_h, 0, u.timezone),
                dt_local(d, start_h + dur_h, 0, u.timezone),
                is_virtual=True,
                location=None,
                is_mandatory=False,
                priority=r.choice([EventPriority.low, EventPriority.medium]),
            )
        )

    reqs: List[MeetingRequest] = []
    standup_days = [hz.start_date + timedelta(days=i) for i in range(5)]
    for i, d in enumerate(standup_days, start=1):
        if _weekday_key(d) in {"sat", "sun"}:
            continue
        reqs.append(
            MeetingRequest(
                request_id=_new_id("req", len(reqs) + 1),
                organizer_id=organizer,
                attendees=team,
                duration_minutes=15,
                deadline=d,
                meeting_type=MeetingType.standup,
                priority=EventPriority.high,
                title_hint=f"Standup D{i}",
            )
        )

    for _ in range(2):
        a, b = r.sample(team, k=2)
        deadline = hz.start_date + timedelta(days=r.randint(2, 7))
        reqs.append(
            MeetingRequest(
                request_id=_new_id("req", len(reqs) + 1),
                organizer_id=a,
                attendees=[a, b],
                duration_minutes=r.choice([30, 45]),
                deadline=deadline,
                meeting_type=MeetingType.ad_hoc,
                priority=EventPriority.medium,
                title_hint="Ad-hoc",
            )
        )

    meta = EnvMeta(
        task_id=task_id,
        seed=0 if seed is None else seed,
        horizon_start=hz.start_date,
        horizon_days=hz.days,
    )
    return EnvironmentState(meta=meta, users=users, events=events, meeting_requests=reqs)


def build_task3(seed: int | None) -> EnvironmentState:
    task_id = "calendar_multi_timezone_robust"
    r = rng_for(task_id, seed)
    hz = ref_horizon(task_id, seed, days=14)

    users = [
        _u("u_ivy", "Ivy Morales", "America/Los_Angeles", ("09:00", "17:00"), cap=3.0, prefer_morning=True),
        _u("u_jules", "Jules Patel", "America/Los_Angeles", ("09:00", "17:00"), cap=3.0, prefer_morning=None),
        _u("u_kai", "Kai Mueller", "Europe/Berlin", ("09:30", "18:00"), cap=3.5, prefer_morning=True),
        _u("u_lee", "Lee Adebayo", "Europe/Berlin", ("09:30", "18:00"), cap=3.5, prefer_morning=False),
        _u("u_mina", "Mina Tanaka", "Asia/Tokyo", ("10:00", "18:30"), cap=3.0, prefer_morning=True),
        _u("u_noah", "Noah Iqbal", "Asia/Kolkata", ("10:00", "18:30"), cap=3.0, prefer_morning=None),
        _u("u_oro", "Oro Silva", "UTC", ("09:00", "17:00"), cap=3.0, prefer_morning=None),
    ]
    team = [u.user_id for u in users]
    organizer = users[2].user_id

    events: List[Event] = []

    for d_off in range(hz.days):
        d = hz.start_date + timedelta(days=d_off)
        if _weekday_key(d) in {"sat", "sun"}:
            continue
        for u in users:
            if r.random() < 0.35:
                start_h = r.choice([10, 11, 14, 15, 16])
                events.append(
                    _seeded_event(
                        _new_id("ev", len(events) + 1),
                        "Blocker-free time",
                        u.user_id,
                        [u.user_id],
                        dt_local(d, start_h, 0, u.timezone),
                        dt_local(d, start_h + 1, 0, u.timezone),
                        is_virtual=False,
                        location="Calendar hold",
                        is_mandatory=False,
                        priority=EventPriority.low,
                    )
                )

    for i in range(4):
        d = hz.start_date + timedelta(days=2 + i * 3)
        if _weekday_key(d) in {"sat", "sun"}:
            continue
        ev = _seeded_event(
            _new_id("ev", len(events) + 1),
            "Release checkpoint",
            organizer,
            team,
            dt_local(d, 15, 0, "Europe/Berlin"),
            dt_local(d, 16, 0, "Europe/Berlin"),
            is_virtual=True,
            location=None,
            is_mandatory=True,
            priority=EventPriority.high,
        )
        events.append(ev)

    reqs: List[MeetingRequest] = []
    reqs.append(
        MeetingRequest(
            request_id=_new_id("req", 1),
            organizer_id=organizer,
            attendees=team,
            duration_minutes=60,
            deadline=hz.start_date + timedelta(days=6),
            meeting_type=MeetingType.sync,
            priority=EventPriority.high,
            title_hint="Weekly sync",
        )
    )
    reqs.append(
        MeetingRequest(
            request_id=_new_id("req", 2),
            organizer_id=organizer,
            attendees=team,
            duration_minutes=120,
            deadline=hz.start_date + timedelta(days=10),
            meeting_type=MeetingType.planning,
            priority=EventPriority.high,
            title_hint="Planning session",
        )
    )
    for idx in range(3, 6):
        a, b, c = r.sample(team, k=3)
        reqs.append(
            MeetingRequest(
                request_id=_new_id("req", idx),
                organizer_id=a,
                attendees=[a, b, c],
                duration_minutes=r.choice([45, 60]),
                deadline=hz.start_date + timedelta(days=r.randint(4, 12)),
                meeting_type=r.choice([MeetingType.review, MeetingType.ad_hoc]),
                priority=r.choice([EventPriority.medium, EventPriority.low]),
                title_hint="Working session",
            )
        )

    meta = EnvMeta(
        task_id=task_id,
        seed=0 if seed is None else seed,
        horizon_start=hz.start_date,
        horizon_days=hz.days,
    )
    st = EnvironmentState(meta=meta, users=users, events=events, meeting_requests=reqs)
    for e in st.events:
        if e.source == "seeded" and e.is_mandatory and e.priority == EventPriority.high:
            st.meta.seeded_mandatory_anchors[e.event_id] = (e.start, e.end)
    return st


TASKS: Dict[str, TaskDef] = {
    "calendar_easy_1v1": TaskDef(
        task_id="calendar_easy_1v1",
        name="Simple 1:1 scheduling",
        description="Schedule one or two short 1:1 requests within working hours without conflicts.",
        difficulty="easy",
        horizon_days=7,
        build=build_task1,
    ),
    "calendar_team_fairness": TaskDef(
        task_id="calendar_team_fairness",
        name="Team scheduling with fairness",
        description="Schedule standups and ad-hoc meetings across two time zones under daily caps and basic fairness.",
        difficulty="medium",
        horizon_days=10,
        build=build_task2,
    ),
    "calendar_multi_timezone_robust": TaskDef(
        task_id="calendar_multi_timezone_robust",
        name="Multi-time-zone robust planning",
        description="Fit multi-day meetings into a 14-day horizon with fairness and stability constraints.",
        difficulty="hard",
        horizon_days=14,
        build=build_task3,
    ),
}


def build_state(task_id: str, seed: int | None) -> EnvironmentState:
    if task_id not in TASKS:
        raise ValueError(f"Unknown task_id: {task_id}")
    st = TASKS[task_id].build(seed)
    st.meta.task_id = task_id
    st.meta.seed = 0 if seed is None else seed
    return st
