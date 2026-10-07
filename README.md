# FAQ semantik qidiruv

Foydalanuvchi savolni o'z so'zlari bilan yozadi, tizim bazadagi eng mos **tasdiqlangan javobni** topib qaytaradi.
Mos javob bo'lmasa buni ochiq aytadi. API (FastAPI) va Telegram bot orqali ishlaydi.

Texnologiyalar: bge-m3 (embedding, Ollama orqali), Qdrant (vektor baza), PostgreSQL (savol-javoblar), FastAPI, aiogram 3.

## Qanday ishlaydi

```
Excel/CSV ──load_data.py──> PostgreSQL (answers, questions)     <- asosiy manba
                                   │
                             build_index.py (bge-m3 embedding)
                                   ▼
                       Qdrant "faq_questions"                    <- qayta quriladigan indeks
                       (har savol = 1 vektor, payload: answer_id)

Foydalanuvchi savoli
  → bge-m3 → Qdrant top-10 savol → answer_id bo'yicha guruhlash (eng yuqori ball)
  → chegara tekshiruvi → PostgreSQL'dan javob matni

Telegram bot ──HTTP──> FastAPI (/ask) ──> yuqoridagi qidiruv
```

Natija uch xil bo'ladi:

| status | Qachon | Nima qaytadi |
|---|---|---|
| `found` | top-1 ball >= `MIN_SCORE` va 2-o'rin yetarlicha uzoq | javob matni |
| `ambiguous` | top-1 va top-2 farqi < `MARGIN` | 2-3 ta variant (savol matni bilan), foydalanuvchi tanlaydi |
| `not_found` | top-1 ball < `MIN_SCORE` | javob yo'q |

## Docker bilan ishga tushirish

Kerak: Docker, hostda o'rnatilgan Ollama va `ollama pull bge-m3`.

1. **Ollama'ni konteynerlarga ochish.** Ollama odatda faqat `127.0.0.1` da tinglaydi, konteynerdan ko'rinmaydi.
   ```bash
   sudo mkdir -p /etc/systemd/system/ollama.service.d
   printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"\n' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
   sudo systemctl daemon-reload && sudo systemctl restart ollama
   ```
   Agar `ufw` yoqilgan bo'lsa: `sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp`.
   (Ollama bo'lmasa, 4-qadamdagi `--profile ollama` variantiga qarang.)
2. **Sozlamalar:** `cp .env.example .env` va ichiga `BOT_TOKEN` ni yozing (bot kerak bo'lmasa ham fayl bo'lishi shart).
3. **Ishga tushirish:**
   ```bash
   docker compose up -d --build
   docker compose ps          # postgres, qdrant, api = healthy; indexer = Exited (0) (bir martalik, normal)
   ```
   `indexer` Excel/CSV'ni Postgres'ga yuklaydi va Qdrant indeksini quradi (CPU'da daqiqalar oladi).
4. **Ixtiyoriy: Ollama ham Docker'da** (hostda Ollama bo'lmasa; ~1.2 GB model yuklanadi):
   `.env` ga `OLLAMA_HOST=http://ollama:11434` yozib, `docker compose --profile ollama up -d --build`.
5. **Tekshirish:** `curl localhost:8001/health`. Swagger: http://localhost:8001/docs

Portlar: Postgres `55432`, Qdrant `6333`, API `8001`.
To'xtatish: `docker compose down` (ma'lumotlarni ham o'chirish: `down -v`).

## Docker'siz ishga tushirish

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
docker compose up -d postgres qdrant          # faqat bazalar Docker'da
python load_data.py                           # yoki: python load_data.py fayl_javoblar.xlsx fayl_savollar.xlsx
python build_index.py
uvicorn api:app --port 8001                   # API
python bot.py                                 # bot (boshqa terminalda)
python search.py                              # terminalda sinab ko'rish
```

## API misollari

```bash
# found
curl -s -X POST localhost:8001/ask -H 'Content-Type: application/json' \
  -d '{"question": "id karta qancha kunda tayyor"}'
# {"status":"found","score":0.927,"answer_id":3,"answer":"Hujjatlar to'liq qabul qilingandan so'ng, ..."}

# ambiguous
curl -s -X POST localhost:8001/ask -H 'Content-Type: application/json' \
  -d '{"question": "ishdan bo‘shatilsam nafaqa olamanmi"}'
# {"status":"ambiguous","score":0.716,"options":[{"answer_id":130,"question":"...","score":0.716}, ...]}

# not_found
curl -s -X POST localhost:8001/ask -H 'Content-Type: application/json' \
  -d '{"question": "bugun havo qanday"}'
# {"status":"not_found","score":0.517}

# ambiguous'dan keyin tanlangan variantning javobi
curl -s localhost:8001/answers/130

# holat: Postgres, Qdrant, Ollama (biri ishlamasa 503)
curl -s localhost:8001/health
```

Ollama, Qdrant yoki Postgres ishlamasa `/ask` 503 va tushunarli xabar qaytaradi (`{"detail": "Qdrant ishlamayapti: ..."}`).

## Telegram bot

Token [@BotFather](https://t.me/BotFather) dan olinadi va `.env` ga `BOT_TOKEN=...` deb yoziladi (kodga yozilmaydi, `.env` git'ga kirmaydi).
Bot qidiruvni o'zi qilmaydi, API'ga HTTP so'rov yuboradi (`API_URL`).
`ambiguous` bo'lsa inline tugmalar chiqadi, bosilganda javob ko'rsatiladi. `not_found` bo'lsa savolni boshqacha yozishni taklif qiladi.

## Sozlamalar

Hammasi `config.py` da, environment o'zgaruvchilaridan olinadi:

| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `DSN` | `postgresql://faq:faq@localhost:55432/faq` | PostgreSQL |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama (Docker'da `http://host.docker.internal:11434`) |
| `EMBED_MODEL` | `bge-m3` | embedding modeli |
| `Q_COLLECTION` | `faq_questions` | Qdrant kolleksiya nomi |
| `TOP_K` | `10` | Qdrant'dan nechta savol olinadi |
| `MIN_SCORE` | `0.60` | shundan past ball -> `not_found` |
| `MARGIN` | `0.03` | top-1 va top-2 farqi shundan kam -> `ambiguous` |
| `BOT_TOKEN` | (bo'sh) | Telegram bot tokeni |
| `API_URL` | `http://localhost:8001` | bot qaysi API'ga murojaat qiladi |

## Loyiha tuzilmasi

```
config.py          sozlamalar
load_data.py       CSV/Excel -> PostgreSQL (idempotent, kirill gomogliflarni tuzatadi)
build_index.py     PostgreSQL -> Qdrant indeksi
search.py          qidiruv mantig'i (found / ambiguous / not_found)
api.py             FastAPI
bot.py             Telegram bot (API orqali)
data/              answers.csv, questions.csv
Dockerfile, docker-compose.yml, .env.example, requirements.txt
```

## Nima uchun shunday qurildi

- **Savol ↔ savol qidiruv.** Javob matnlari emas, bazadagi *savollar* indekslanadi: foydalanuvchi savoli va bazadagi savol bir xil turdagi matn, o'xshashlik ishonchliroq. Har javobga ~6 savol bor, shuning uchun bitta javob turli shakllarda "ushlanadi".
- **LLM yo'q.** Tasdiqlangan javob aynan qaytariladi: hallucination yo'q, tez, javob manbasi aniq.
- **Framework yo'q** (LlamaIndex/LangChain). Retrieval LLM'siz bo'lgani uchun ortiqcha qatlam.
- **bge-m3.** Ko'p tilli, o'zbekchani qo'llaydi, lokal ishlaydi.
- **PostgreSQL + Qdrant.** Postgres asosiy manba (javob matnlari), Qdrant faqat qayta quriladigan indeks (qaysi `answer_id`).
- Faqat faol savollar/javoblar indekslanadi. Telefon apostroflari (‘ ’ ` ʼ ʻ) oddiy `'` ga o'tkaziladi. Lotin matn ichidagi kirill harf (masalan "egа") yuklashda avtomatik tuzatiladi.

## Sifat qanday tekshirildi va natija

**1. Avtomatik tekshiruv.** Har javobdan 1 ta savol (jami 505) testga ajratildi va indeksga qo'shilmadi, qolgan 2543 savol indekslandi (test savoli o'zini o'zi topib olmasligi uchun). Natija: **Top-1 99.8%, Recall@3 100%, MRR 0.999**. Yagona xato `ambiguous` qoidasi bilan ushlandi.
Lekin test savollari shablon bo'yicha yasalgan paraphrase'lar, shuning uchun **bu baho oshirilgan**.

**2. Mavzudan tashqari 20 ta savol** (ob-havo, retsept, futbol...). Eng yuqori ball 0.677. `MIN_SCORE` bo'yicha xato javob berilgan savollar: 0.60 → 4/20, 0.65 → 1/20, 0.70 → 0/20.

**3. Qo'lda yozilgan 38 ta so'zlashuv savoli** (33 mavzuga oid, 5 mavzudan tashqari; savollar va "to'g'ri javob"ni AI yordamchi belgilagan, shuning uchun taxminiy baho):

| Natija | Soni |
|---|---|
| `found` va to'g'ri | 20 |
| `ambiguous`, variantlar ichida to'g'risi bor | 6 |
| `found`, lekin noto'g'ri javob | 6 |
| `not_found`, aslida javob bor edi (bir so'zli "ta'til") | 1 |
| Mavzudan tashqari: to'g'ri `not_found` | 5/5 |

Ya'ni mavzuga oid savollarning ~79% to'g'ri javob yoki to'g'ri variantlar bilan qaytdi, ~18% ishonch bilan **noto'g'ri** javob oldi. Noto'g'rilari mavzusi yaqin javoblar edi (masalan "ta'til bermayapti" → "ish haqi kechiktirilsa"), ballari 0.70–0.81, shuning uchun chegara ularni ushlamaydi.

**4. Servislar:** `docker compose up` dan keyin hamma servis healthy, Postgres'da 505/3048, Qdrant'da 3048 ta yozuv, `/ask` uch holatni ham to'g'ri qaytardi, `/health` hammasi ok. Bot tokensiz tekshirilmadi.

## Cheklovlar

- Mavzu yaqin, javob boshqa bo'lgan holatlar eng katta muammo; `MARGIN` faqat ballar deyarli teng bo'lganda ishlaydi.
- `MIN_SCORE=0.60` kelishuv: mavzudan tashqari ba'zi savollarga javob berishi mumkin; 0.70 da esa haqiqiy savollarning bir qismi `not_found` bo'ladi.
- Juda qisqa so'rovlar ("ta'til") kontekst bermaydi. Kirill yozuvdagi savol bitta sinovda ishladi, sistematik tekshirilmadi.
- CPU'da model xotirada turganda so'rov ~0.06 s, model xotiradan chiqib ketsa birinchi so'rov sekin. Indekslash daqiqalar oladi.
- Test to'plamlari kichik va tarafdor; ishonchli baho uchun real foydalanuvchi savollari kerak.

## Keyingi qadamlar

1. **Reranker** (masalan bge-reranker): yaqin javoblar muammosiga eng to'g'ridan-to'g'ri yechim.
2. **Hybrid BM25 + vektor:** aniq so'zlar yo'qolib qolmasligi uchun.
3. **Noaniq zonada LLM-as-judge:** ball 0.65–0.80 oralig'ida LLM faqat nomzodlardan birini tanlaydi (javob yozmaydi).
4. **Foydalanuvchi feedback'i** ("foydali bo'ldimi?" tugmasi) asosida `MIN_SCORE` va `MARGIN` ni sozlash.
5. **Monitoring:** `not_found` va `ambiguous` so'rovlarni yig'ish, bazada nima yetishmayotganini ko'rish.
