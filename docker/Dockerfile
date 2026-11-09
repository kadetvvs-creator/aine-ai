FROM python:3.12-slim

WORKDIR /app

# Код AINE (движок использует только стандартную библиотеку — зависимостей нет)
COPY code/ail.py /app/ail.py
COPY code/self_improve.py /app/self_improve.py
COPY code/benchmark.py /app/benchmark.py
COPY code/web_learn.py /app/web_learn.py
COPY code/ai_docs.py /app/ai_docs.py

# Движок генома живёт в /app/ail.py; саморазвитие — /app/self_improve.py
ENV GENOME_PATH=/app/genome.json
ENV LLAMA_URL=http://llama-server:8080
ENV EMBED_URL=http://embed:8084

CMD ["python3", "/app/self_improve.py"]
