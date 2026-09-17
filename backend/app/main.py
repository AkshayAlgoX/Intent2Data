import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.pipeline.models import AnalyzeResponse
from app.pipeline.orchestrator import PipelineError
from app.runtime import RuntimeState, load_runtime
from app.settings import Settings

logger = logging.getLogger("intent2data.api")

APP_VERSION = "0.2.0"
CONTRACT_VERSION = "v1"
# Bounds on the research question. The upper bound exists because the question
# text is forwarded verbatim into every LLM prompt; an unbounded string is an
# unbounded token bill.
QUESTION_MIN_CHARS = 3
QUESTION_MAX_CHARS = 2000
REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Index + LLM client are built once here, never in the request path.
    app.state.runtime = load_runtime(Settings.from_env())
    yield


app = FastAPI(title="Intent2Data API", version=APP_VERSION, lifespan=lifespan)

# Demo frontend origin(s). Comma-separated list; "*" is acceptable for the
# hackathon demo because the API sets no cookies and has no credentials.
_cors_origins = [
    o.strip() for o in os.getenv("INTENT2DATA_CORS_ORIGINS", "*").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)


class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=QUESTION_MIN_CHARS, max_length=QUESTION_MAX_CHARS)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < QUESTION_MIN_CHARS:
            raise ValueError("question must not be blank")
        return stripped


def get_runtime(request: Request) -> RuntimeState:
    return request.app.state.runtime


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request.headers.get(REQUEST_ID_HEADER, "")


def _error(request: Request, status: int, message: str, **extra) -> JSONResponse:
    rid = _request_id(request)
    return JSONResponse(status_code=status, content={"error": message, "request_id": rid, **extra},
                        headers={REQUEST_ID_HEADER: rid})


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    # Echo a caller-supplied id (so the frontend can correlate) or mint one.
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Shape matches contracts/v1/error_response.json: a top-level "error" string.
    return _error(request, 422, "Invalid request parameters.", detail=jsonable_encoder(exc.errors()))


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # Never leak stack traces or provider error bodies to the client; log them
    # with the request id so they can be found.
    logger.exception("unhandled error request_id=%s", _request_id(request))
    return _error(request, 500, "Internal server error.")


@app.get("/health")
def health_check(runtime: RuntimeState = Depends(get_runtime)):
    body = {"status": "ok" if runtime.ready else "degraded", "ready": runtime.ready}
    if runtime.index is not None:
        body["index"] = runtime.index.stats()
    if runtime.index_error:
        body["error"] = runtime.index_error
    return body


@app.get("/version")
def version():
    return {"version": APP_VERSION, "contract": CONTRACT_VERSION}


@app.post("/v1/analyze", response_model=AnalyzeResponse, response_model_exclude_none=False)
def analyze(req: AnalyzeRequest, request: Request, runtime: RuntimeState = Depends(get_runtime)):
    if not runtime.ready:
        return _error(request, 503, "Runtime index not available.", detail=runtime.index_error or "not loaded")
    try:
        return runtime.pipeline().run(req.question, _request_id(request))
    except PipelineError as exc:
        status = 502 if exc.retryable else 422
        logger.warning("pipeline error request_id=%s stage=%s msg=%s", _request_id(request), exc.stage, exc.message)
        return _error(request, status, exc.message, stage=exc.stage, retryable=exc.retryable)
