FROM python:3.12-slim

WORKDIR /app

# Avval faqat requirements: kod o'zgarganda kutubxonalar qayta o'rnatilmaydi (cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY data ./data

# Root bo'lmagan foydalanuvchi bilan ishlatamiz
RUN useradd --create-home app
USER app

# Standart buyruq: API. Boshqa servislar compose'da o'z buyrug'ini beradi.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8001"]
