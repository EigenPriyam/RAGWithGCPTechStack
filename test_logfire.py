"""
Quick Logfire smoke-test.

Sends traces to logfire.dev using the token from .env.
View results at: https://logfire.pydantic.dev

Run:
    uv run python test_logfire.py
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()

import logfire
from pydantic import BaseModel, ValidationError

# ── Configure Logfire — sends to logfire.dev ──────────────────────────────────
logfire.configure(
    token=os.environ["LOGFIRE_TOKEN"],
    send_to_logfire=True,
    console=False,          # disable console; view traces on logfire.dev instead
    service_name="rag-test",
)

print("Logfire configured. Sending traces to logfire.dev ...")

# ── 1. Basic log messages ─────────────────────────────────────────────────────
logfire.info("Logfire is working", version="4.33.0")
logfire.debug("Debug message")
logfire.warning("This is a warning", component="test_script")


# ── 2. Nested spans ───────────────────────────────────────────────────────────
with logfire.span("ingest-document") as span:
    span.set_attribute("doc_id", "doc_001")
    span.set_attribute("file_type", "pdf")
    time.sleep(0.05)

    with logfire.span("parse-pdf"):
        logfire.info("Parsing PDF pages", page_count=12)
        time.sleep(0.02)

    with logfire.span("chunk-text"):
        logfire.info("Splitting into chunks", chunk_size=512, overlap=64)
        time.sleep(0.01)

logfire.info("Document ingestion complete")


# ── 3. Structured attributes ───────────────────────────────────────────────────
with logfire.span("vector-search") as span:
    span.set_attribute("query", "What is RAG?")
    span.set_attribute("top_k", 5)
    span.set_attribute("collection", "enterprise_docs")
    results = [{"id": f"chunk_{i}", "score": round(0.95 - i * 0.05, 2)} for i in range(5)]
    span.set_attribute("results_count", len(results))
    logfire.info("Search complete", results=str(results))


# ── 4. Exception recording ─────────────────────────────────────────────────────
with logfire.span("risky-operation"):
    try:
        raise ValueError("Simulated upstream timeout")
    except ValueError as exc:
        logfire.exception("Caught expected error during test", error=str(exc))


# ── 5. Pydantic model validation tracing ──────────────────────────────────────
logfire.instrument_pydantic()

class Document(BaseModel):
    doc_id: str
    title: str
    page_count: int

with logfire.span("validate-documents"):
    doc = Document(doc_id="d1", title="GCP Architecture Guide", page_count=42)
    logfire.info("Valid document", doc_id=doc.doc_id, title=doc.title)

    try:
        Document(doc_id="d2", title="Bad Doc", page_count="not-a-number")
    except ValidationError as exc:
        logfire.warning("Validation failed (expected)", errors=exc.error_count())


# ── 6. LLM latency simulation ─────────────────────────────────────────────────
with logfire.span("llm-generate") as span:
    start = time.perf_counter()
    time.sleep(0.08)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    span.set_attribute("latency_ms", latency_ms)
    span.set_attribute("model", "gemini-2.0-flash")
    span.set_attribute("tokens_generated", 256)
    logfire.info("LLM response ready", latency_ms=latency_ms)


logfire.info("All tests complete — check https://logfire.pydantic.dev")
print("Done. Open https://logfire.pydantic.dev to view your traces.")
