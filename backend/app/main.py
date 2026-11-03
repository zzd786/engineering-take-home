import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from app.api import router
from app.logging_config import configure_logging, request_id_context
from app.metrics import LATENCY, REQUESTS
from app.product_metrics import ProductCollector

configure_logging()
logger = logging.getLogger("diary.requests")

REGISTRY.register(ProductCollector())

app = FastAPI(title="Symptom Diary API")
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo submitted values, parser details or arbitrary field names.
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.perf_counter()
    request_id = str(uuid4())  # Never trust caller-supplied IDs in logs.
    context_token = request_id_context.set(request_id)
    error_kind = None
    try:
        try:
            response = await call_next(request)
        except Exception:
            # Exception messages and tracebacks can contain SQL parameters and health data.
            error_kind = "unexpected"
            response = JSONResponse(
                status_code=500, content={"detail": "An unexpected error occurred."}
            )
        route = request.scope["route"].path if "route" in request.scope else "unmatched"
        elapsed = time.perf_counter() - started
        method = (
            request.method
            if request.method
            in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}
            else "OTHER"
        )
        REQUESTS.labels(method, route, response.status_code).inc()
        LATENCY.labels(method, route).observe(elapsed)
        fields = {
            "method": method,
            "route": route,
            "status": response.status_code,
            "duration_ms": round(elapsed * 1000, 2),
        }
        if response.status_code >= 500:
            fields["error_kind"] = error_kind or "service"
            logger.error("request_failed", extra=fields)
        else:
            logger.info("request_completed", extra=fields)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_context.reset(context_token)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
