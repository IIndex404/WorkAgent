# 复用已有向量服务

`compose.yml` 会下载并运行一份 BGE。如果机器上已经有可用的向量服务，可以另写 `compose.local.yml`，去掉默认的 `embedding` 服务，让应用连接现有服务。

下面是 Docker 共享网络的例子。`my-embedding-network` 和 `my-embedding` 要换成你的实际网络名与容器名。

```yaml
name: workagent
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: workagent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: workagent
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U workagent -d workagent"]
      interval: 5s
      timeout: 3s
      retries: 20
  app:
    build: .
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://workagent:${POSTGRES_PASSWORD}@postgres:5432/workagent
      EMBEDDING_BASE_URL: http://my-embedding/v1
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - ./data:/app/data
      - ./app/static/avatars:/app/app/static/avatars
    networks: [default, embeddings]
    depends_on:
      postgres:
        condition: service_healthy
volumes:
  postgres_data:
networks:
  embeddings:
    external: true
    name: my-embedding-network
```

启动命令：

```bash
docker compose -f compose.local.yml up -d --build --wait
```

这份本地配置不会被 Git 提交。已有数据库换模型时，要先核对维度；同样是 BGE，不同型号的输出维度也可能不同。仓库默认的 `bge-small-zh-v1.5` 是512维。
