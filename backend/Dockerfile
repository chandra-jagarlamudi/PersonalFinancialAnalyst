FROM python:3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml /app/
COPY pfa /app/pfa

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "pfa.main:app", "--host", "0.0.0.0", "--port", "8000"]
