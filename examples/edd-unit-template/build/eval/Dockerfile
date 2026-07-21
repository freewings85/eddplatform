# 评估程序 worker 镜像（docker context = 仓库根，COPY 整个 eval/）
FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple \
    "temporalio>=1.7" "httpx>=0.27" "pydantic-evals>=2,<3"
WORKDIR /app
COPY eval/ .
CMD ["python", "worker.py"]
