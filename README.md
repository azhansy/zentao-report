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

## 许可证建议

开源前建议补充 LICENSE（MIT/Apache-2.0 等）和 CONTRIBUTING 文档。

**月报（当月）**：

```python
def get_current_month_range():
    today = datetime.date.today()
    start = today.replace(day=1)
    end = (start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    return start, end
```

## 🔧 工作流程

```
1. 连接禅道 API
   ├─ 登录认证
   └─ 获取 session token

2. 获取任务数据
   ├─ 按时间范围筛选
   ├─ 按成员分组
   └─ 统计任务状态

3. 生成报告
   ├─ 格式化为 Markdown
   ├─ 添加统计信息
   └─ 保存到 build/ 目录

4. 推送飞书（可选）
   └─ 通过 Webhook 发送
```

## ❗ 常见问题

### 1. 无法连接禅道

**原因**：URL、用户名或密码错误

**解决**：
- 检查 `.env` 中的配置
- 确认禅道 URL 可以访问
- 验证用户名密码是否正确
- 检查禅道 API 是否开启

### 2. 飞书推送失败

**原因**：Webhook 地址错误或权限不足

**解决**：
- 确认 Webhook 地址正确
- 检查机器人是否被添加到群聊
- 查看飞书机器人的权限设置

### 3. 中文乱码

确保脚本使用 UTF-8 编码：

```python
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)
```

### 4. 时间范围不对

根据需求修改时间计算逻辑，注意时区问题。

## 📝 使用技巧

### 1. 定时运行

使用 cron 定时生成报告：

```bash
# 每周一早上9点生成上周报告
0 9 * * 1 cd /path/to/zentao && python zentao_task.py

# 每月1号生成上月报告
0 9 1 * * cd /path/to/zentao && python zentao_monthly_task.py
```

### 2. 自定义过滤

在脚本中添加任务过滤逻辑：

```python
def filter_tasks(tasks):
    # 只显示特定项目的任务
    return [t for t in tasks if t['project'] == '核心项目']
    
    # 只显示高优先级任务
    return [t for t in tasks if t['pri'] >= 3]
```

### 3. 导出 Excel

使用 `pandas` 导出 Excel：

```python
import pandas as pd

df = pd.DataFrame(tasks)
df.to_excel('build/tasks.xlsx', index=False)
```

### 4. 多群推送

配置多个 Webhook：

```python
WEBHOOKS = [
    "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx",  # 技术群
    "https://open.feishu.cn/open-apis/bot/v2/hook/yyyyy",  # 管理群
]

for webhook in WEBHOOKS:
    send_to_feishu(webhook, content)
```

## 🎓 新手提示

1. **第一次使用**：
   - 先确认能访问禅道系统
   - 获取 API 文档（通常在 `/doc` 路径）
   - 测试 API 连接

2. **调试技巧**：
   - 使用 `print()` 查看 API 返回数据
   - 先测试获取少量数据
   - 检查 HTTP 状态码和错误信息

3. **权限问题**：
   - 确保用户有查看任务的权限
   - 某些禅道版本需要管理员权限
   - 检查 API 访问是否被限制

4. **数据理解**：
   - 任务状态：wait, doing, done, closed, cancel
   - 优先级：1-4（1最高）
   - 任务类型：开发、测试、Bug等

## 🔄 集成其他系统

### 集成钉钉

替换飞书 Webhook 为钉钉格式：

```python
def send_to_dingtalk(webhook, content):
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "周报",
            "text": content
        }
    }
    requests.post(webhook, json=payload)
```

### 集成企业微信

```python
def send_to_wechat(webhook, content):
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }
    requests.post(webhook, json=payload)
```

### 生成图表

使用 `matplotlib` 生成任务统计图表：

```python
import matplotlib.pyplot as plt

# 任务状态分布
labels = ['完成', '进行中', '等待']
sizes = [12, 2, 1]
plt.pie(sizes, labels=labels, autopct='%1.1f%%')
plt.savefig('build/task_stats.png')
```

# 进入容器构建程序包
、、、
scp -r . ab@192.168.9.5:/Users/ab/docker/ql/data/scripts/zentao
docker exec -it qinglong bash
pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
pyinstaller --clean --noconfirm zentao_main.spec
cp -r ./zentao/dist/zentao_main/ ./zentao_main
# 复制配置文件到容器
scp zentao.ini ab@192.168.9.5:/Users/ab/docker/ql/data/scripts/zentao_main/zentao.ini
```

## 📚 相关资源

- [禅道开源版文档](https://www.zentao.net/book/zentaopmshelp.html)
- [禅道 API 文档](https://www.zentao.net/book/api/)
- [飞书机器人文档](https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN)
- [钉钉机器人文档](https://open.dingtalk.com/document/robots/custom-robot-access)
