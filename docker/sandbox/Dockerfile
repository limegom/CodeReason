FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0

RUN groupadd --gid 65532 sandbox \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin sandbox \
    && mkdir -p /runner /input \
    && chown -R 65532:65532 /runner /input \
    && chmod 0555 /runner /input

COPY --chown=65532:65532 runner.py security_policy.py /runner/

USER 65532:65532
WORKDIR /tmp

ENTRYPOINT ["/usr/local/bin/python", "/runner/runner.py"]
CMD ["--stdin-request"]
