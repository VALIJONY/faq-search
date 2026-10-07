"""PostgreSQL'dagi faol savollarni embedding qilib, Qdrant'ga yuklaydi (indeksni noldan quradi)."""
import logging

import psycopg
from qdrant_client import models

from config import DSN, Q_COLLECTION, VECTOR_SIZE
from search import embed, qdrant

log = logging.getLogger("build_index")


def fetch_questions() -> list[dict]:
    """Postgres'dan faqat faol savollarni (faol javoblarga tegishli) olamiz."""
    sql = """
        SELECT q.id, q.answer_id, q.question
        FROM questions q
        JOIN answers a ON a.id = q.answer_id
        WHERE q.is_active AND a.status = 'active'
    """
    with psycopg.connect(DSN) as conn:
        rows = conn.execute(sql).fetchall()
    return [{"id": r[0], "answer_id": r[1], "question": r[2]} for r in rows]


def build_collection(name: str, questions: list[dict], batch: int = 32) -> int:
    """Kolleksiyani o'chirib qaytadan yaratadi. Point id = Postgres'dagi savol id."""
    if qdrant.collection_exists(name):
        qdrant.delete_collection(name)
    qdrant.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
    )

    for i in range(0, len(questions), batch):
        part = questions[i:i + batch]
        vectors = embed([q["question"] for q in part])
        points = [
            models.PointStruct(id=q["id"], vector=v, payload={"answer_id": q["answer_id"], "question": q["question"]})
            for q, v in zip(part, vectors)
        ]
        qdrant.upsert(collection_name=name, points=points)
        log.info("%d/%d", i + len(part), len(questions))

    return qdrant.count(name).count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    n = build_collection(Q_COLLECTION, fetch_questions())
    log.info("Tayyor: %s = %d ta savol", Q_COLLECTION, n)
