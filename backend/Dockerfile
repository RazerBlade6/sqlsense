# One image for both Lambda functions: the API (app.lambda_handler.handler) and the corpus
# ingest custom resource (app.retrieval.ingest.handler). Build context: the repository root.
FROM public.ecr.aws/lambda/python:3.13

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_NO_CACHE=1

COPY backend/pyproject.toml backend/uv.lock /tmp/build/
RUN cd /tmp/build \
    && uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt \
    && uv pip install --python /var/lang/bin/python3 --target "${LAMBDA_TASK_ROOT}" -r requirements.txt \
    && rm -rf /tmp/build

ENV CATALOG_PATH=${LAMBDA_TASK_ROOT}/catalog/retail.yaml \
    CORPUS_PATH=${LAMBDA_TASK_ROOT}/corpus
COPY catalog/retail.yaml ${LAMBDA_TASK_ROOT}/catalog/retail.yaml
COPY corpus ${LAMBDA_TASK_ROOT}/corpus
COPY backend/app ${LAMBDA_TASK_ROOT}/app

CMD ["app.lambda_handler.handler"]
