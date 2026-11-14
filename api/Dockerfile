FROM python:3.14.9-slim-trixie AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
WORKDIR /srv
COPY api/requirements.txt api/requirements.txt
RUN pip install -r api/requirements.txt
COPY pkg/ pkg/
COPY api/app/ api/app/
RUN useradd --system --uid 10001 app
WORKDIR /srv/api

FROM base AS runtime
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test
COPY api/requirements-dev.txt requirements-dev.txt
RUN pip install -r requirements-dev.txt
COPY api/tests/ tests/
USER app
CMD ["pytest", "-q", "-p", "no:cacheprovider"]
