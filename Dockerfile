ARG BASE_IMAGE=nlm-api-base:latest
FROM ${BASE_IMAGE}

WORKDIR /app
COPY app /app/app
COPY scripts/entrypoint.sh /app/scripts/entrypoint.sh

RUN chmod +x /app/scripts/entrypoint.sh

EXPOSE 8080 6080

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
