FROM python:3.12-slim
ARG VCS_REF=unknown
ARG BUILD_CREATED=unknown
LABEL org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.created="$BUILD_CREATED"
WORKDIR /app
# APP_REVISION is expanded while the image is built from the immutable VCS_REF
# build argument. It remains part of the image configuration rather than an
# App Service setting, so a still-serving older container reports its own
# revision during a rolling replacement.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_REVISION=$VCS_REF
COPY requirements.lock .
RUN python -m pip install --no-cache-dir --upgrade pip==26.1.2 \
    && python -m pip install --no-cache-dir -r requirements.lock
COPY . .
RUN test -f /app/scripts/seed_rivermere_demo.py
RUN mkdir -p /app/data
RUN chmod +x /app/entrypoint.sh
CMD ["/app/entrypoint.sh"]
