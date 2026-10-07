"""Qidiruv mantig'i: savol -> embedding -> Qdrant -> javoblar bo'yicha guruhlash -> found/ambiguous/not_found."""
import logging

import ollama
import psycopg
from qdrant_client import QdrantClient

from config import (DSN, EMBED_MODEL, MARGIN, MIN_SCORE, OLLAMA_HOST, Q_COLLECTION,
                    QDRANT_URL, TOP_K)

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # har HTTP so'rovni log'ga yozmasin

qdrant = QdrantClient(url=QDRANT_URL)
ollama_client = ollama.Client(host=OLLAMA_HOST)


class ServiceError(Exception):
    """Ollama, Qdrant yoki Postgres ishlamayotganda ko'tariladi (xabari foydalanuvchiga ko'rsatilsa bo'ladi)."""


def clean(text: str) -> str:
    """Telefondagi o‘ / o’ apostroflarini bazadagi oddiy ' ga keltiramiz."""
    for ch in "‘’`ʼʻ":
        text = text.replace(ch, "'")
    return text.strip()


def embed(texts: list[str]) -> list[list[float]]:
    """Matnlar ro'yxatini bge-m3 orqali vektorlarga aylantiradi (bitta so'rovda, batch)."""
    try:
        return ollama_client.embed(model=EMBED_MODEL, input=texts)["embeddings"]
    except Exception as e:
        log.error("Ollama xatosi: %s", e)
        raise ServiceError(f"Ollama (embedding) ishlamayapti: {OLLAMA_HOST}") from e


def group_by_answer(hits: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """[(answer_id, ball), ...] -> har javobdan eng yuqori ball, eng yaxshisi birinchi.

    Bitta javobning bir nechta savoli top-10 ga tushishi mumkin, shuning uchun guruhlaymiz.
    """
    best: dict[int, float] = {}
    for answer_id, score in hits:
        best[answer_id] = max(best.get(answer_id, 0.0), score)
    return sorted(best.items(), key=lambda x: x[1], reverse=True)


def rank(vector: list[float], collection: str = Q_COLLECTION, top_k: int = TOP_K) -> list[tuple[int, float]]:
    """Tayyor vektor bo'yicha Qdrant'dan qidiradi va javoblar bo'yicha guruhlaydi."""
    try:
        points = qdrant.query_points(collection_name=collection, query=vector, limit=top_k).points
    except Exception as e:
        log.error("Qdrant xatosi: %s", e)
        raise ServiceError(f"Qdrant ishlamayapti: {QDRANT_URL}") from e
    return group_by_answer([(p.payload["answer_id"], p.score) for p in points])


def find_candidates(question: str, collection: str = Q_COLLECTION, top_k: int = TOP_K) -> list[tuple[int, float]]:
    """Eng mos javoblar: [(answer_id, ball), ...] — eng yaxshisi birinchi."""
    return rank(embed([clean(question)])[0], collection, top_k)


def _fetch_one(sql: str, params: tuple):
    try:
        with psycopg.connect(DSN, connect_timeout=5) as conn:
            return conn.execute(sql, params).fetchone()
    except psycopg.Error as e:
        log.error("Postgres xatosi: %s", e)
        raise ServiceError("PostgreSQL ishlamayapti") from e


def get_answer(answer_id: int) -> str | None:
    """Javob matni (topilmasa None)."""
    row = _fetch_one("SELECT answer FROM answers WHERE id = %s", (answer_id,))
    return row[0] if row else None


def get_question(answer_id: int) -> str:
    """Tugma matni uchun: shu javobning birinchi savoli."""
    row = _fetch_one("SELECT question FROM questions WHERE answer_id = %s ORDER BY id LIMIT 1", (answer_id,))
    return row[0] if row else ""


def search(question: str) -> dict:
    """Natija: {"status": "found" | "ambiguous" | "not_found", ...}"""
    candidates = find_candidates(question)

    # 1) Hech narsa yetarlicha o'xshash emas
    if not candidates or candidates[0][1] < MIN_SCORE:
        return {"status": "not_found", "score": round(candidates[0][1], 3) if candidates else 0.0}

    top_id, top_score = candidates[0]

    # 2) Ikkilanish: keyingi javoblar ham deyarli bir xil ball olgan (eng ko'pi bilan 3 ta variant)
    close = [(aid, sc) for aid, sc in candidates[:3] if top_score - sc < MARGIN and sc >= MIN_SCORE]
    if len(close) > 1:
        return {
            "status": "ambiguous",
            "score": round(top_score, 3),
            "options": [{"answer_id": aid, "question": get_question(aid), "score": round(sc, 3)}
                        for aid, sc in close],
        }

    # 3) Aniq javob
    return {"status": "found", "answer_id": top_id, "answer": get_answer(top_id), "score": round(top_score, 3)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    while True:
        q = input("\nSavol (chiqish: Enter): ").strip()
        if not q:
            break
        try:
            for aid, sc in find_candidates(q)[:3]:
                print(f"  {sc:.3f}  answer_id={aid}")
            r = search(q)
        except ServiceError as e:
            print("Xato:", e)
            continue
        print("\n" + (r.get("answer") or f"[{r['status']}]"))
