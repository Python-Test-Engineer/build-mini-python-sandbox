# Dockerfile - the sandbox image for the mini Python coding harness.
#
# Design rules:
#   * one purpose: run Python tools, not a general desktop;
#   * non-root user with a fixed uid:gid so the runner can pass --user;
#   * no package manager use at runtime; the image is built once and pinned;
#   * no writable application directory except the mounted workspace and the
#     tmpfs mounts supplied by docker_runner.py.
#
# Build from this directory:
#
#   docker build -t mini-harness-python:latest .
#
# Pin the base image by digest in production, for example:
#   FROM python:3.12-slim-bookworm@sha256:<digest>

FROM python:3.12-slim-bookworm

# OCI labels make it obvious which image is running in `docker image ls`.
LABEL org.opencontainers.image.title="mini-harness-python"
LABEL org.opencontainers.image.description="Sandbox image for a mini Python coding harness"

# Create a fixed, unprivileged user. The numeric uid:gid is what the runner
# passes with --user, so the name here is for humans and logs.
RUN groupadd --gid 1000 sandbox \
    && useradd --uid 1000 --gid sandbox --create-home --shell /usr/sbin/nologin sandbox \
    && mkdir -p /workspace \
    && chown sandbox:sandbox /workspace

# Deterministic Python behaviour inside the container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONIOENCODING=utf-8

# The only bind mount is expected at /workspace. Everything else is read-only
# at runtime because docker_runner.py passes --read-only.
WORKDIR /workspace
USER sandbox

# A harmless default. The runner always supplies its own argv after the image
# name, so this command is only used when someone runs the image directly.
CMD ["python", "-c", "print('mini-harness sandbox image ready')"]
