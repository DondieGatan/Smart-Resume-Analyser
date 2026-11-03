# Hugging Face Spaces build of the app. Spaces run the container as a non-root user (uid 1000),
# so the NLTK data, the sentence-transformers model and the uploads folder all live under that
# user's home instead of /root or a root-owned /app. The Render build (../../Dockerfile) is unchanged.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860 \
    NLTK_DATA=/home/user/nltk_data \
    HF_HOME=/home/user/.cache/huggingface

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the language data and the embedding model at build time so the first request does not
# pay for it (the Space can then also start with no outbound access).
RUN python -c "import nltk; [nltk.download(p, quiet=True) for p in ['punkt','punkt_tab','averaged_perceptron_tagger','averaged_perceptron_tagger_eng','stopwords','maxent_ne_chunker','maxent_ne_chunker_tab','words']]"
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY --chown=user . .
RUN mkdir -p uploads

EXPOSE 7860
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 120 app:app"]
