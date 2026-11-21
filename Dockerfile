# Imagem de producao (Easypanel / qualquer Docker).
#
# Um unico processo uvicorn: o tempo real (telao, carrossel, notificacoes) e o
# limitador de login ficam na memoria do processo. NAO rode com mais de uma
# replica nem com --workers > 1.
#
# Todos os dados ficam em /data (banco SQLite, fotos, backups, chave de
# identificacao, chaves do push). Monte um volume persistente em /data, senao
# cada atualizacao apaga tudo. Ver docs/publicar-easypanel.md.

# ---------------------------------------------------------------- frontend
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- backend
FROM python:3.13-slim-bookworm
# EXIGIR_VOLUME_DADOS: sem volume montado em /data o sistema NAO sobe (em vez
# de subir com banco vazio e perder tudo no proximo deploy).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    EXIGIR_VOLUME_DADOS=1

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Usuario sem privilegios (uid 1000). A pasta montada em /data precisa
# pertencer a ele: chown -R 1000:1000 <pasta no servidor>.
RUN useradd --uid 1000 --create-home sorteio \
    && mkdir -p /data \
    && chown sorteio:sorteio /data
USER sorteio

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/saude', timeout=4)"

# HTTPS fica no proxy do Easypanel; --proxy-headers faz o sistema enxergar o
# IP real de quem acessa (auditoria e limite de tentativas de login).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
