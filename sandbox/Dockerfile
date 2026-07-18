FROM python:3.12-slim

WORKDIR /app

COPY --chown=nobody:nogroup target_repo/ /app/target_repo/

RUN pip install --no-cache-dir pytest

USER nobody

CMD ["pytest", "-q", "-p", "no:cacheprovider"]
