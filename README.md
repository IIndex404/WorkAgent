# WorkAgent | 企业内部业务智能体

本项目由 [IIndex404](https://github.com/IIndex404) 独立开发并维护。

开源许可：MIT。随项目分发的第三方依赖许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

Git 克隆、提交与推送操作见 [Git 使用说明](docs/git-workflow.md)。

把公司制度问答和日常请假流程放在一个页面里。

员工可以查制度、核对原文、提交请假；管理员在后台处理申请，员工再回来查看结果。问答用 DeepSeek 生成回答，资料检索可以用本地 BGE 模型，不需要另外购买向量接口。

## 怎么用

**查制度**

问“入职满一年有几天年假？”时，系统先从知识库找相关内容，再回答问题。回答里的 `[1]` 对应下方的参考资料，点开文档名就能看到原文片段。普通闲聊不会附上资料。

**请假**

员工登录后，在“我的请假”填写类型、日期和事由。管理员进入“请假审批”，填写意见后批准或驳回。员工刷新申请列表，就能看到结果、审批人和处理时间。

员工只能查看自己的申请。重复提交重叠日期、重复审批，以及员工直接调用管理员接口，都会被后端拦截。

## 本地运行

需要 Docker 和 Docker Compose。默认配置会启动应用、PostgreSQL 和本地 BGE 向量服务。

```bash
git clone https://github.com/IIndex404/WorkAgent.git
cd WorkAgent
cp .env.example .env
```

Windows PowerShell 的复制命令是 `Copy-Item .env.example .env`。

打开 `.env`，填写这四项：

```dotenv
LLM_API_KEY=你的DeepSeek密钥
POSTGRES_PASSWORD=自行设置的数据库密码
JWT_SECRET=一段足够长的随机字符串
ADMIN_PASSWORD=自行设置的管理员密码
```

数据库密码请使用字母和数字，避免数据库连接地址里的特殊字符转义问题。向量模型的配置可以先保持默认。

```bash
docker compose up -d --build --wait
```

首次启动需要下载镜像和模型，时间取决于网络。模型就绪后，应用会把 `data/` 中的 TXT 资料建立索引。仓库只提供 `data/example-policy.txt` 这份虚构演示资料。

| 页面 | 地址 |
| --- | --- |
| 用户端 | http://127.0.0.1:8000/ |
| 管理后台 | http://127.0.0.1:8000/admin |
| 接口文档 | http://127.0.0.1:8000/docs |

管理员用户名默认是 `admin`，密码就是刚才填写的值。员工可以在用户端注册账号。

```bash
# 看日志
docker compose logs --tail 100 app

# 停止服务，保留数据
docker compose stop

# 修改 .env 后应用配置
docker compose up -d --force-recreate --wait app
```

已经创建的管理员不会因为修改 `.env` 而自动重置密码。`ADMIN_PASSWORD` 只用于首次创建账号。

Windows 也可以使用 `start.cmd`、`stop.cmd` 和 `apply-config.cmd`。如果目录里有自己的 `compose.local.yml`，这三个脚本会优先使用它。

## 已有向量服务的情况

不用重复下载模型。应用可以连接 OpenAI 兼容的向量接口，也可以复用已有的 TEI 服务。

本地 TEI 的配置示例：

```dotenv
EMBEDDING_PROVIDER=tei
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_BASE_URL=http://你的向量服务地址/v1
EMBEDDING_API_KEY=
EMBEDDING_DIM=512
USE_RERANK=0
```

应用运行在容器里时，`127.0.0.1` 指的是应用容器本身。复用另一个容器，需要配置共享网络或可访问的服务地址。可参考 [已有向量服务的部署方式](docs/reuse-embedding.md)。

模型维度必须和数据库向量字段一致。切换成其他维度的模型时，需要迁移字段并重新建立索引，单改 `.env` 不够。

## 代码放在哪里

```text
app/
  routers/       登录、问答、文档管理和请假接口
  services/      检索、引用来源、问答和记忆
  graph/         LangGraph 工具调用与通知审批示例
  models.py      用户、知识块、对话、请假和审批记录
  static/        Vue 用户端与管理后台
data/            虚构演示资料；可以在后台上传自己的 TXT 文档
tests/           接口、权限、检索和流式问答测试
```

后端用 FastAPI，业务数据和对话记忆存在 PostgreSQL，向量检索用 pgvector。检索会合并向量结果与 BM25 关键词结果，前端用 Vue 3，回答通过 SSE 逐段显示。

## 测试

服务启动后可以运行：

```bash
docker compose exec app python -m pytest -q --disable-warnings
```

目前回归测试为 **45 项通过、3 项跳过**。覆盖了申请人隔离、审批权限、日期校验、重叠申请、重复审批、引用来源、流式错误和对话记忆。跳过的是默认关闭的三个文档集成测试。

真实接口另验证过：本地 BGE 检索、DeepSeek 带引用回答，以及两个审批请求同时处理同一申请时只有一个生效。网页也走过了提交、审批、刷新后查看结果的流程。

## 目前的边界

- 请假按自然日计算，包含起止日期，暂不计算工作日，也不自动扣减年假余额。
- 知识库目前接收 UTF-8 TXT。仓库仅包含明确标注为虚构的功能演示资料，实际使用时请自行配置有权使用的资料。
- 计算、天气和发通知的工具示例仍然保留。通知尚未接入真实消息平台，天气接口失败时可能返回标明来源的演示缓存。
- 当前默认只允许本机访问。给其他电脑使用时，需要另外配置访问地址、HTTPS 等部署项。
- 这版还没有做到按员工隔离聊天历史和知识库；请假接口已经做了员工隔离。开放给多人使用前，还需要补齐聊天会话的服务端鉴权。
