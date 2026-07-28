FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ARG TOOLS_UID=1000
ARG TOOLS_GID=1000

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock

RUN set -eu; \
    if ! getent group "${TOOLS_GID}" >/dev/null 2>&1; then \
        groupadd --gid "${TOOLS_GID}" tools; \
    fi; \
    if ! getent passwd "${TOOLS_UID}" >/dev/null 2>&1; then \
        useradd --uid "${TOOLS_UID}" --gid "${TOOLS_GID}" \
            --home-dir /home/tools --create-home --shell /usr/sbin/nologin tools; \
    fi

WORKDIR /workspace
USER ${TOOLS_UID}:${TOOLS_GID}
ENTRYPOINT ["python"]
