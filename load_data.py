"""Savol-javoblarni CSV yoki Excel (.xlsx) fayldan PostgreSQL'ga yuklaydi. Qayta ishga tushirsa ham dublikat bo'lmaydi.

Ishlatish:  python load_data.py [answers_fayl] [questions_fayl]
"""
import logging
import re
import sys

import pandas as pd
import psycopg

from config import DSN

log = logging.getLogger("load_data")

SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    id          INTEGER PRIMARY KEY,
    category_id INTEGER,
    topic_id    INTEGER,
    answer      TEXT NOT NULL,
    status      TEXT,
    created_at  TIMESTAMP,
    updated_at  TIMESTAMP
);
CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY,
    answer_id   INTEGER NOT NULL REFERENCES answers(id),
    question    TEXT NOT NULL,
    is_active   BOOLEAN,
    created_at  TIMESTAMP,
    updated_at  TIMESTAMP
);
"""

# Lotin harfga juda o'xshash kirill harflar (gomogliflar): kirill -> lotin
HOMOGLYPHS = str.maketrans("аеорсхуіАВЕКМНОРСТХ", "aeopcxyiABEKMHOPCTX")
LATIN = re.compile(r"[A-Za-z]")
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
WORD = re.compile(r"[\w'‘’ʻʼ`-]+")


def fix_homoglyphs(text: str, where: str) -> str:
    """Lotin so'z ichiga adashib kirill harf tushgan bo'lsa (masalan 'egа'), uni lotinga almashtiradi.

    Faqat aralash (lotin + kirill) so'zlar o'zgaradi; toza kirill so'zlarga tegilmaydi.
    """
    def fix_word(m: re.Match) -> str:
        word = m.group()
        if LATIN.search(word) and CYRILLIC.search(word):
            fixed = word.translate(HOMOGLYPHS)
            level = logging.WARNING if CYRILLIC.search(fixed) else logging.INFO
            log.log(level, "%s: aralash yozuv %r -> %r", where, word, fixed)
            return fixed
        return word

    return WORD.sub(fix_word, text)


def read_table(path: str) -> pd.DataFrame:
    """CSV ham, Excel ham qabul qilinadi. Bo'sh qiymatlar (NaN) None bo'ladi."""
    df = pd.read_excel(path) if path.endswith((".xlsx", ".xls")) else pd.read_csv(path)
    return df.astype(object).where(df.notna(), None)


def main(answers_path: str = "data/answers.csv", questions_path: str = "data/questions.csv") -> None:
    answers = read_table(answers_path)
    questions = read_table(questions_path)

    missing = set(questions["answer_id"]) - set(answers["id"])
    if missing:
        raise SystemExit(f"Javobi yo'q savollar bor: answer_id={sorted(missing)[:10]}")

    answers["answer"] = [fix_homoglyphs(t, f"javob {i}") for i, t in zip(answers["id"], answers["answer"])]
    questions["question"] = [fix_homoglyphs(t, f"savol {i}") for i, t in zip(questions["id"], questions["question"])]

    a_cols = ["id", "category_id", "topic_id", "answer", "status", "created_at", "updated_at"]
    q_cols = ["id", "answer_id", "question", "is_active", "created_at", "updated_at"]

    with psycopg.connect(DSN) as conn:
        conn.execute(SCHEMA)
        with conn.cursor() as cur:
            # ON CONFLICT: skriptni qayta ishga tushirsak, bor qatorlar yangilanadi, dublikat bo'lmaydi
            cur.executemany(
                f"""INSERT INTO answers ({", ".join(a_cols)}) VALUES ({", ".join(["%s"] * len(a_cols))})
                    ON CONFLICT (id) DO UPDATE SET category_id=EXCLUDED.category_id, topic_id=EXCLUDED.topic_id,
                    answer=EXCLUDED.answer, status=EXCLUDED.status, updated_at=EXCLUDED.updated_at""",
                answers[a_cols].itertuples(index=False),
            )
            cur.executemany(
                f"""INSERT INTO questions ({", ".join(q_cols)}) VALUES ({", ".join(["%s"] * len(q_cols))})
                    ON CONFLICT (id) DO UPDATE SET answer_id=EXCLUDED.answer_id, question=EXCLUDED.question,
                    is_active=EXCLUDED.is_active, updated_at=EXCLUDED.updated_at""",
                questions[q_cols].itertuples(index=False),
            )
        n_a = conn.execute("SELECT count(*) FROM answers").fetchone()[0]
        n_q = conn.execute("SELECT count(*) FROM questions").fetchone()[0]
    log.info("Yuklandi: %d ta javob, %d ta savol", n_a, n_q)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main(*sys.argv[1:3])
