FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.lock .
RUN python -m pip install --no-cache-dir --upgrade pip==26.1.2 \
    && python -m pip install --no-cache-dir -r requirements.lock
COPY . .
RUN cp /app/mobile/participant-app/assets/citizen-centric-logo.png /app/app/static/citizen-centric-logo.png \
    && cp /app/mobile/participant-app/assets/citizen-centric-logo-compact.png /app/app/static/citizen-centric-logo-compact.png
RUN mkdir -p /app/data
RUN chmod +x /app/entrypoint.sh
CMD ["/app/entrypoint.sh"]
