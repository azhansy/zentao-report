# Zentao 基于禅道开源版21.5脚本

从禅道 API 拉取任务和 Bug 数据，按日/周/月/周期生成统计并推送到飞书。

## 功能概览

- 多项目多 webhook 映射推送
- 每人每日待处理 Bug 提醒
- 周/月任务统计
- 周/月 Bug 统计
- 周期统计（季度/半年/年度）
- token 缓存（默认 24 小时）

## 目录说明

- `zentao_main.py`：统一入口
- `zentao_config.py`：配置加载与用户映射
- `zentao_utils.py`：登录、时间处理、飞书发送等工具
- `zentao.ini.example`：配置模板（可提交）
- `zentao.ini`：本地配置（敏感信息，勿提交）
- `users.example.json`：用户映射模板（可提交）
- `users.json`：本地用户映射（含人员标识，勿提交）

## 开源前安全清单

1. 只提交 `zentao.ini.example`，不要提交 `zentao.ini`
2. 不要提交 `.zentao_token_cache`
3. 不要在 README、脚本注释里保留真实 webhook、账号、密码
4. 发布前执行一次敏感信息扫描（例如 `rg "password|webhook|token" zentao`）

## 快速开始

### 1. 准备配置

```bash
cd zentao
cp zentao.ini.example zentao.ini
cp users.example.json users.json
```

编辑 `zentao.ini`：

```ini
[zentao]
base_url = https://your-zentao-domain/zentao/api.php/v1
web_url = https://your-zentao-domain/zentao
username = your_username
password = your_password

[api]
page = 1
limit = 300

[feishu]
# 可选默认 webhook
webhook = https://open.feishu.cn/open-apis/bot/v2/hook/your-default-webhook

[project_webhook_map]
# key 格式：project_id_product_id
2_1 = https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-a
27_5 = https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-b

[display]
fixed_user_width = 8
```

说明：

- `project_webhook_map` 为主配置，支持多个项目/产品同时推送
- `feishu.webhook` 是兜底值（可留空，但建议配置）
- 用户映射默认读取 `users.json`，也可通过环境变量 `ZENTAO_USERS_FILE` 指定

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

如果仓库根目录没有统一依赖文件，至少安装：

```bash
pip install requests
```

### 3. 验证配置

```bash
python zentao_config.py
```

### 4. 运行任务

```bash
# 查看帮助
python zentao_main.py

# 任务 1：每日待处理 bug
python zentao_main.py 1

# 任务 2：本周 bug
python zentao_main.py 2

# 任务 3：本周任务
python zentao_main.py 3

# 任务 4：本月 bug
python zentao_main.py 4

# 任务 5：本月任务
python zentao_main.py 5

# 任务 6：任务跟进监控
python zentao_main.py 6

# 任务 7：周期统计（支持 period 参数）
python zentao_main.py 7 --period half
```

## 配置文件查找顺序

`zentao_config.py` 会按以下顺序查找配置：

1. 当前工作目录：`zentao.ini`
2. 可执行文件目录（打包模式）
3. 脚本目录（开发模式）
4. 用户目录：`~/.zentao.ini`

## 常见问题

- 配置了 `zentao.ini.example` 但不生效：
  程序读取的是 `zentao.ini`

- webhook 推送目标不对：
  检查 `project_webhook_map` 的 key 是否为 `project_id_product_id`

- 周期报告类型：
  可选值通常为 `quarter`、`half`、`year`（具体以入口参数为准）

## 📚 相关资源

- [禅道开源版文档](https://www.zentao.net/book/zentaopmshelp.html)
- [禅道 API 文档](https://www.zentao.net/book/api/)
- [飞书机器人文档](https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN)

## 构建与发布

### 本地构建

使用 PyInstaller 构建单平台可执行文件。

**前置条件**：
```bash
pip install -r requirements.txt
pip install pyinstaller
```

**构建命令**：
```bash
pyinstaller --clean --noconfirm zentao_main.spec
```

输出文件位于 `dist/zentao_main/` 目录。

### 多平台自动构建

本项目配置了 GitHub Actions 工作流 (`.github/workflows/build.yml`)，支持自动构建以下平台的可执行文件：

- **Linux** (x64)
- **macOS** (Intel x64)
- **macOS** (Apple Silicon ARM64)
- **Windows** (x64)

**触发方式**：

1. **标签发布**（推荐）：创建新的 git tag 并 push
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
   GitHub Actions 会自动构建并在 Release 页面上传二进制文件。

2. **手动触发**：在 GitHub 仓库的 Actions 标签页选择 "Build Multi-Platform Executables" 工作流并手动运行。

**发布工件**：
- 构建输出会自动上传到 GitHub Artifacts（保留 30 天）
- 标签发布时，二进制文件会附加到 Release 页面供下载

## 开源协议

本项目使用 MIT License，详见 `LICENSE`。
