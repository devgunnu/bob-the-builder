FROM public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 AS lambda-adapter
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8080 AWS_LWA_INVOKE_MODE=response_stream \
    AWS_LWA_READINESS_CHECK_PATH=/api/ping BOB_EMBED_MODEL_PATH=/opt/models/potion-base-8M
COPY --from=lambda-adapter /lambda-adapter /opt/extensions/lambda-adapter
COPY backend/ /app/backend/
RUN pip install --no-cache-dir /app/backend && \
    python -c "from model2vec import StaticModel; StaticModel.from_pretrained('minishlab/potion-base-8M').save_pretrained('/opt/models/potion-base-8M')"
COPY infra/templates/ /app/infra/templates/
# The demo corpus is optional during development; the complete build includes it when present.
COPY . /app/
RUN mkdir -p /app/demo
CMD ["uvicorn", "bob.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
