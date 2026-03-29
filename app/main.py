from __future__ import annotations

import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import TypeAdapter

from .baseline import run_baseline_for_all_tasks
from .env import ACTIVE_ENV
from .grader import grade
from .models import *
from .tasks import TASKS

app = FastAPI(title="calendar_meeting_scheduler_env")

@app.get("/", response_class=HTMLResponse)
def home():
    return "<h1>FINAL WORKING BUILD v10 </h1>"

@app.post("/reset")
def reset(inp):
    st = ACTIVE_ENV.reset(inp.task_id, inp.seed)
    return {"state": st}

@app.post("/step")
def step(inp):
    st, reward, done = ACTIVE_ENV.step(inp.task_id, inp.action)
    return {"state": st, "reward": reward, "done": done}

@app.get("/tasks")
def tasks():
    return list(TASKS.keys())

def run():
    uvicorn.run("app.main:app", host="0.0.0.0", port=7860)