FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src \
    HPAPP_DB_PATH=/data/hpapp.db HPAPP_HOST=0.0.0.0 HPAPP_PORT=8080
RUN useradd --system --uid 10001 app && mkdir -p /data && chown app /data
WORKDIR /app
COPY src ./src
USER app
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2).status==200 else 1)"
CMD ["python", "-m", "hpapp.main"]
