FROM python:3.11-slim

# System dependencies: just the Tesseract OCR binary (pytesseract is a
# Python wrapper around it). psycopg[binary] bundles its own libpq, so no
# system Postgres client library is needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download NLTK data at build time so the first request doesn't pay for
# it (and doesn't fail if the container has no outbound access at runtime).
RUN python -c "import nltk; [nltk.download(p, quiet=True) for p in ['punkt','punkt_tab','averaged_perceptron_tagger','averaged_perceptron_tagger_eng','stopwords','maxent_ne_chunker','maxent_ne_chunker_tab','words']]"

COPY . .

EXPOSE 10000
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 120 app:app"]
