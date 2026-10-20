# Git 使用说明

仓库：https://github.com/IIndex404/WorkAgent

默认分支：`main`。

## 获取项目

```bash
git clone https://github.com/IIndex404/WorkAgent.git
cd WorkAgent
git status
```

运行前复制 `.env.example` 为 `.env` 并填写配置，详见 [README](../README.md)。

## 提交和推送修改

在项目目录中执行：

```bash
git status
git diff
git add README.md
git diff --cached
git commit -m "docs: update project documentation"
git push
```

将 `README.md` 换成需要提交的实际文件路径。首次发布已配置 `main` 跟踪 `origin/main`，后续可直接运行 `git push`。推送需要当前 GitHub 账号拥有仓库写入权限。

## 使用功能分支

开始新功能前，在工作区干净时同步主分支：

```bash
git switch main
git pull --ff-only
git switch -c feature/my-feature
```

完成修改并提交后，首次推送分支：

```bash
git push -u origin feature/my-feature
```

随后可在 GitHub 创建 Pull Request。

## 查看历史和远程地址

```bash
git log --oneline -10
git remote -v
```

## 本地配置与数据

`.gitignore` 排除 `.env`、本地部署配置、用户上传资料、头像、数据库文件、日志、虚拟环境和缓存；`.env.example` 与虚构功能演示资料保留在仓库中。

提交前检查 `git diff --cached`，确保没有真实密钥、公司内部文档或个人数据。已有文件一旦被 Git 跟踪，新增忽略规则不会自动取消跟踪。

`.gitattributes` 统一源码和文档的换行符，Windows 启动脚本使用 CRLF。
