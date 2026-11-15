FROM python:3.14.9-slim-trixie AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
WORKDIR /srv/simulators
COPY simulators/requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY simulators/sim/ sim/
RUN useradd --system --uid 10001 app

FROM base AS runtime
USER app
ENTRYPOINT ["python", "-m", "sim"]
CMD ["run"]

FROM base AS test
COPY simulators/requirements-dev.txt requirements-dev.txt
RUN pip install -r requirements-dev.txt
COPY simulators/tests/ tests/
USER app
CMD ["pytest", "-q", "-p", "no:cacheprovider"]
