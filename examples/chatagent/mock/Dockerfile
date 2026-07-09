# 本地 mock datamanager（纯 stdlib，无依赖）：给 searchshops/searchcoupons 提供固定假数据。
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY mock_datamanager.py .
ENV MOCK_DATAMANAGER_PORT=50401
EXPOSE 50401
CMD ["python", "mock_datamanager.py"]
