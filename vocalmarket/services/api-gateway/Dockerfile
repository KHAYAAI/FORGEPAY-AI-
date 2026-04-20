FROM python:3.12-slim

WORKDIR /app

RUN pip install poetry==1.8.3 && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-dev --no-interaction --no-ansi

COPY src/ ./vocalmarket/services/api-gateway/src/
COPY ../../shared/ ./vocalmarket/shared/

EXPOSE 8000
CMD ["uvicorn", "vocalmarket.services.api-gateway.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
