FROM python:3.11-slim

WORKDIR /code
COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY __init__.py ./backend/__init__.py
COPY app/ ./backend/app/
ENV PYTHONPATH=/code

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
