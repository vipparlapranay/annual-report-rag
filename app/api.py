from contextlib import asynccontextmanager
import logging
from time import perf_counter

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.answering import ReportAnswerer
from app.config import settings
from app.documents import chunk_text, load_document
from app.schemas import AskRequest, AskResponse, HealthResponse, IngestResponse
from app.vector_store import ReportStore

logger = logging.getLogger("annual_report_rag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = ReportStore()
    app.state.store = store
    app.state.answerer = ReportAnswerer(store)
    app.state.request_metrics = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "latency_ms_total": 0.0,
    }
    yield


app = FastAPI(
    title="Annual Report RAG API",
    description="Citation-grounded answers over uploaded annual reports.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    store: ReportStore = app.state.store
    return HealthResponse(status="ok", indexed_chunks=store.count)


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    started = perf_counter()
    response = app.state.answerer.ask(request.question, request.top_k)
    metrics = app.state.request_metrics
    metrics["requests"] += 1
    metrics["input_tokens"] += response.input_tokens
    metrics["output_tokens"] += response.output_tokens
    metrics["estimated_cost_usd"] += response.estimated_cost_usd
    metrics["latency_ms_total"] += (perf_counter() - started) * 1000
    logger.info(
        "request_metrics",
        extra={
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "estimated_cost_usd": response.estimated_cost_usd,
            "abstained": response.abstained,
        },
    )
    return response


@app.post("/documents", response_model=IngestResponse, status_code=201)
async def ingest(file: UploadFile = File(...)) -> IngestResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")
    if len(file.filename) > 255:
        raise HTTPException(status_code=400, detail="Filename is too long.")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Document exceeds upload limit.")
    try:
        pages = load_document(file.filename, content)
        chunks = [
            chunk
            for text, page in pages
            for chunk in chunk_text(
                text,
                file.filename,
                page,
                settings.chunk_size,
                settings.chunk_overlap,
            )
        ]
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        if file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Could not read the PDF.") from error
        raise
    if not chunks:
        raise HTTPException(status_code=400, detail="Document contains no readable text.")
    return IngestResponse(
        document=file.filename,
        chunks_indexed=app.state.store.add(chunks),
    )


@app.get("/metrics")
def metrics() -> dict[str, int | float]:
    stats = app.state.request_metrics
    requests = stats["requests"]
    return {
        **stats,
        "average_latency_ms": (
            stats["latency_ms_total"] / requests if requests else 0.0
        ),
    }
