"""Barcha sozlamalar shu yerda. Qiymatlar environment o'zgaruvchilaridan olinadi."""
import os

from dotenv import load_dotenv

load_dotenv()  # .env fayl bo'lsa, undagi qiymatlarni o'qiydi (Docker'da compose o'zi beradi)

# Bazalar va model
DSN = os.getenv("DSN", "postgresql://faq:faq@localhost:55432/faq")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
Q_COLLECTION = os.getenv("Q_COLLECTION", "faq_questions")
VECTOR_SIZE = 1024  # bge-m3 vektor o'lchami, o'zgarmaydi

# Qidiruv qoidalari
TOP_K = int(os.getenv("TOP_K", "10"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.60"))  # shundan past bo'lsa -> not_found
MARGIN = float(os.getenv("MARGIN", "0.03"))        # top-1 va top-2 farqi shundan kam bo'lsa -> ambiguous

# Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_URL = os.getenv("API_URL", "http://localhost:8001")
