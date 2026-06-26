"""QueueStorm Investigator — AI/API support copilot for digital finance.

Exposes the two endpoints the judge harness exercises (spec §4):
  - GET  /health         → {"status": "ok"}
  - POST /analyze-ticket → structured investigation of one ticket

Prometheus instrumentation (/metrics) is retained as an engineering
differentiator (tie-breaker #5) and is not on the judge's required path.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from api.errors import register_exception_handlers
from api.routes import router

app = FastAPI(
    title="QueueStorm Investigator",
    version="1.0.0",
    description="Reads a complaint plus recent transactions, decides what happened, routes it, and drafts a safe reply.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
register_exception_handlers(app)

Instrumentator().instrument(app).expose(app)
