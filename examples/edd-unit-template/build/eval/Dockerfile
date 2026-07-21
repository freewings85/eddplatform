# 评估程序 worker 镜像（docker context = 仓库根，COPY 整个 eval/）
FROM python:3.12-slim-bookworm
# 用 pydantic-evals 内置 LLMJudge 时，加装模型 provider（如 "pydantic-ai-slim[openai]"）
# 并配 OPENAI_BASE_URL/OPENAI_API_KEY（走平台「部署配置(.env.eval)」注入）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple \
    "temporalio>=1.7" "httpx>=0.27" "pydantic-evals>=2,<3"
WORKDIR /app
COPY eval/ .
CMD ["python", "worker.py"]
