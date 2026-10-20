# WorkAgent 应用镜像
# 构建：docker build -t workagent .
# 运行：docker run -p 8000:8000 --env-file .env workagent

FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码与数据
COPY app ./app
COPY tests ./tests
COPY data ./data

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
