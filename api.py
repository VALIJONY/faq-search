"""FastAPI: POST /ask, GET /answers/{id}, GET /health."""
import logging
from typing import Literal

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import DSN, OLLAMA_HOST, QDRANT_URL
from search import ServiceError, get_answer, qdrant, search

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="FAQ semantik qidiruv", description="Savolni ma'no bo'yicha qidirib, tasdiqlangan javobni qaytaradi.")


@app.exception_handler(ServiceError)
async def service_error_handler(request, exc: ServiceError):
    """Ollama/Qdrant/Postgres ishlamasa, 500 traceback o'rniga tushunarli 503 xabar."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    model_config = {"json_schema_extra": {"examples": [{"question": "id karta qancha kunda tayyor bo'ladi"}]}}


class Option(BaseModel):
    answer_id: int
    question: str
    score: float


class AskResponse(BaseModel):
    status: Literal["found", "ambiguous", "not_found"]
    score: float
    answer_id: int | None = None   # faqat found
    answer: str | None = None      # faqat found
    options: list[Option] | None = None  # faqat ambiguous

    model_config = {"json_schema_extra": {"examples": [
        {"status": "found", "score": 0.91, "answer_id": 1, "answer": "Yangi ID-karta ... 1 ish kuni ichida ..."},
        {"status": "ambiguous", "score": 0.74, "options": [
            {"answer_id": 231, "question": "Birinchi savol", "score": 0.74},
            {"answer_id": 127, "question": "Ikkinchi savol", "score": 0.72}]},
        {"status": "not_found", "score": 0.41},
    ]}}


class AnswerResponse(BaseModel):
    answer_id: int
    answer: str


@app.post("/ask", response_model=AskResponse, response_model_exclude_none=True)
def ask(body: AskRequest):
    """Savolga javob qidiradi. status: found | ambiguous | not_found."""
    return search(body.question)


@app.get("/answers/{answer_id}", response_model=AnswerResponse,
         responses={404: {"description": "Bunday javob yo'q"}})
def answer(answer_id: int):
    """Ambiguous holatda foydalanuvchi tanlagan variantning javobini qaytaradi."""
    text = get_answer(answer_id)
    if text is None:
        raise HTTPException(404, "Javob topilmadi")
    return {"answer_id": answer_id, "answer": text}


@app.get("/health")
def health():
    """Postgres, Qdrant va Ollama holatini tekshiradi. Biri ishlamasa 503."""
    checks = {}
    try:
        with psycopg.connect(DSN, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"xato: {e}"
    try:
        qdrant.get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = f"xato: {e}"
    try:
        httpx.get(OLLAMA_HOST, timeout=3).raise_for_status()
        checks["ollama"] = "ok"
    except Exception as e:
        checks["ollama"] = f"xato: {e}"

    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(status_code=200 if healthy else 503, content={"status": "ok" if healthy else "error", **checks})
