---
title: Calendar Meeting Scheduler
colorFrom: blue
colorTo: green
sdk: docker
app_file: app/main.py
pinned: false
---
 
 ## Calendar Meeting Scheduler OpenEnv
 
 This repository provides `calendar_meeting_scheduler_env`, an OpenEnv-style HTTP environment that simulates how a small organization schedules meetings across multiple users, time zones, and personal calendars.
 
 The environment exposes a simple workflow:
 - **Reset** into one of three tasks to generate users, existing events, and pending meeting requests.
 - **Step** by creating meetings, moving events, or canceling non-mandatory events.
 - **Grade** a final state snapshot for a task-specific score in \([0.0, 1.0]\).
 
 ### State (observation)
 The state is JSON with:
 - **users**: people with `timezone`, weekday `work_hours`, and scheduling preferences (daily cap, preferred times).
 - **events**: all scheduled calendar events (owner + attendees, start/end timestamps, priority, mandatory flag).
 - **meeting_requests**: pending requests that must be scheduled (duration, attendees, deadline, type, priority).
 - **metadata**: task id, seed, horizon window, and counters.
 
 ### Actions
 The environment supports these action variants:
 - **create_meeting**: schedule an event for a specific meeting request id.
 - **move_event**: reschedule an existing event.
 - **cancel_event**: remove an event (not allowed for mandatory events).
 - **noop**: take no action.
 
 Actions are validated with Pydantic models; `/tasks` returns the action schema.
 
 ### Tasks
- **`calendar_easy_1v1` (easy)**: 2-3 users in one time zone, 1-2 short 1:1 requests, few conflicts.
- **`calendar_team_fairness` (medium)**: 4-5 users across two time zones, daily standup + ad-hoc meetings, daily caps and fairness.
- **`calendar_multi_timezone_robust` (hard)**: 6-8 users across >=3 time zones, mandatory events, multi-day planning, fairness + stability.
 
 ### What the grader optimizes
Each task's grade is a weighted combination of:
 - **coverage**: fraction of meeting requests that are scheduled with correct duration and deadlines
 - **conflicts**: overlap-free calendars across all users
- **working-hours compliance**: meetings fall inside each attendee's working hours
- **fairness** (tasks 2-3): avoids repeatedly assigning the worst local times to the same person
 - **stability** (task 3): does not move high-priority mandatory events
 
 ### Run locally (uv)
 From the repo root:
 
 ```bash
 uv run server
 ```
 
 The server listens on `0.0.0.0:7860`.
 
 ### Run the baseline
 
 ```bash
 uv run baseline
 ```
 
 This runs a naive deterministic scheduler for all tasks and prints `{task_id: score}`.
 
 ### Assumptions / limitations
 - The environment uses an in-memory active episode (single-process, single active task instance).
- Timestamps are ISO-8601 and include offsets; time zone behavior uses Python's `zoneinfo`.
 - The baseline is intentionally simple and not globally optimal.

<!-- rebuild trigger -->