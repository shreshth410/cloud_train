FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 OMP_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY trainer/pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip PIP_NO_CACHE_DIR=0 pip install "scikit-learn==1.5.*" "xgboost==2.1.*" "pandas==2.2.*" "numpy<2.1" "joblib" "boto3" "jsonschema" "pyarrow"
COPY trainer/cloudtrain_trainer ./cloudtrain_trainer
COPY shared /app/shared
RUN useradd -m trainer && chown -R trainer /app
USER trainer
ENTRYPOINT ["python", "-m", "cloudtrain_trainer.main"]
