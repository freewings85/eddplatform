FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple \
    "temporalio>=1.7" "httpx>=0.27" "pydantic-evals>=2,<3"
WORKDIR /app
COPY worker.py edd_bridge.py ./
CMD ["python", "worker.py"]
