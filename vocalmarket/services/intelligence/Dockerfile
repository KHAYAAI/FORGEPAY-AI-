FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install poetry && poetry config virtualenvs.create false && poetry install --no-dev

COPY . ./vocalmarket/services/intelligence/

ENV PYTHONPATH=/app
CMD ["uvicorn", "vocalmarket.services.intelligence.main:app", "--host", "0.0.0.0", "--port", "8004"]
