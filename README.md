# MindTrack AI — OpenAI + 账号系统联网版

已实现：

- 用户邮箱注册 / 六位验证码验证 / 登录 / 退出
- SQLite 用户数据库
- PBKDF2-SHA256 密码哈希
- 30 天 Bearer Session
- 每个账号独立聊天记录
- 后端调用 OpenAI Responses API
- API Key 只保存在服务器
- 危机关键词先走安全分流
- FastAPI REST API

## 本地启动

```bash
python -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

安装：

```bash
pip install -r requirements.txt
```

设置 OpenAI API Key。

macOS / Linux:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-5.6-luna"
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_MODEL="gpt-5.6-luna"
```

启动：

```bash
uvicorn server:app --reload
```

打开：

```text
http://127.0.0.1:8000
```

## 联网部署

这个版本必须部署 Python 后端，不能只上传静态 HTML。

部署平台需要：

- Python Web Service
- HTTPS
- 环境变量 / Secrets
- 持久化磁盘，或将 SQLite 换成 PostgreSQL

Start Command:

```bash
uvicorn server:app --host 0.0.0.0 --port $PORT
```

环境变量：

```text
OPENAI_API_KEY=你的 OpenAI API Key
OPENAI_MODEL=gpt-5.6-luna
```

生产环境建议再加入：

- PostgreSQL
- 忘记密码 / 重置密码
- 登录限流 / CAPTCHA
- HttpOnly Secure Cookie
- 更严格 CORS
- 数据删除 / 导出
- API 成本和请求限额
- 更完整的心理健康危机分类器
- 隐私政策与服务条款

## OpenAI 接入位置

`server.py` 中使用：

```python
client = OpenAI(api_key=OPENAI_API_KEY)
response = client.responses.create(
    model=OPENAI_MODEL,
    input=items,
    max_output_tokens=500
)
```

不要把 API Key 写到 `app.js` 或 `index.html`。

## 邮箱注册配置

在服务器环境变量中设置 `RESEND_API_KEY` 和 `EMAIL_FROM`（Resend API Key 及已验证域名的发件地址）。可选设置 `GOOGLE_CLIENT_ID` 以启用 Google 登录。重启后端后配置才会生效。

`.env.example` 仅提供配置模板。后端会自动加载项目目录中的 `.env`，已有的系统环境变量优先。复制模板为 `.env`，填入真实值，然后运行：

```bash
uvicorn server:app --reload
```

不要提交真实密钥。前端只公开 `index.html`、`app.js` 和 `styles.css`。

注册成功会发送有效期 10 分钟的六位验证码，验证成功后自动登录。未验证账号不能登录。未收到邮件或验证码过期时，等待至少 60 秒后重新注册以获取新验证码；新验证码会替换旧验证码。每个验证码最多允许 5 次错误尝试。

## 回归检查

测试使用临时数据库和模拟邮件，不会发送真实邮件或修改现有数据库。

```bash
python -m unittest discover -s tests -v
node tests/test_frontend.cjs
```

## Render 部署检查

在已有 Render **Web Service** 的 Settings 中核对：

- Build Command：`pip install -r requirements.txt`
- Start Command：`uvicorn server:app --host 0.0.0.0 --port $PORT`
- Health Check Path：`/api/health`
- 公网地址使用 Render 提供的 `https://...onrender.com`。

前后端由同一个服务提供，`fetch("/api/...")` 自动跟随当前域名与 HTTPS，不需要改成 localhost 或写死公网域名。Render 负责 HTTPS 证书及 HTTP 到 HTTPS 的跳转；后端正常监听 HTTP 即可。生产启动不要使用 `--reload`。

在 Render 的 Environment 中单独设置 `OPENAI_API_KEY`、`OPENAI_MODEL`、`RESEND_API_KEY`、`EMAIL_FROM`，以及可选的 `GOOGLE_CLIENT_ID`。本机 `.env` 不会随 Git 自动部署，不要将它提交到仓库。同源部署不用设置 `CORS_ORIGINS`；如果前端单独部署，再填前端的完整 HTTPS origin。

### 邮件与存储限制

验证码邮件已改为 Resend HTTPS API（443 端口），不再使用 Gmail SMTP，因此不依赖 Render Free 封锁的 SMTP 端口。旧的 `GMAIL_ADDRESS` 和 `GMAIL_APP_PASSWORD` 不再被程序读取。

在 Resend 创建有发信权限的 API Key，并验证你拥有的发件域名，然后在本机 `.env` 和 Render Environment 分别配置：

```dotenv
RESEND_API_KEY=你的Resend密钥
EMAIL_FROM=MindTrack AI <verify@你的已验证域名>
```

不要把示例域名直接用于真实发信。普通 `@gmail.com` 地址以及 Render 分配的 `onrender.com` 域名不能作为你拥有并可配置 DNS 的发件域名。网站仍可使用 Render 域名，邮件使用你另行验证的域名。

没有域名时可用 `EMAIL_FROM=MindTrack AI <onboarding@resend.dev>` 进行 Resend 测试，但只能发给注册 Resend 账号所用的邮箱；面向其他用户注册前必须验证自己的域名。API 接收成功不等于最终投递成功，未收到时检查垃圾邮件和 Resend 邮件日志。

保存配置后重启本地后端；线上需推送代码并在 Render 保存环境变量、重新部署。服务不会自动回退 SMTP，也不会向浏览器暴露验证码。发信超时或失败仍回滚本次注册变更。

参考：[Resend 发信 API](https://resend.com/docs/api-reference/emails/send-email)、[验证域名](https://resend.com/docs/dashboard/domains/introduction)。

SQLite 默认写入项目目录。Render 的普通文件系统是临时的，重启或重新部署会丢失注册账号、会话和聊天记录。要保留当前 SQLite 实现，需要在付费服务挂载持久化磁盘，例如 `/var/data`，再设置 `DB_PATH=/var/data/mindtrack.db`。该目录必须存在并且可写，服务保持单实例。更改路径会打开新数据库，不会自动迁移旧数据；已有数据请先备份并迁移。Free 实例不能挂持久化磁盘，需要另行迁移到外部数据库。

免费实例冷启动可能需要约一分钟。前端允许连接等待 90 秒，并在连接期间禁用重复提交；临时网络故障不会清除浏览器保存的登录凭证。

当前仓库不含 `render.yml`；通过控制台创建的 Web Service 可以直接自动部署，不要求该文件。修改本地文件后需提交并推送到 Render 关联的分支，才会触发自动部署。

参考：[Render Web Services](https://render.com/docs/web-services)、[Free 限制](https://render.com/docs/free)、[持久化磁盘](https://render.com/docs/disks)。

### 确认线上已经切换到 Resend

部署后访问 `/api/health`：`email_provider` 应为 `resend`，`email_configured` 应为 `true`。如果没有这两个字段，线上尚未运行这一版代码；如果配置为 `false`，请检查 Render Environment 并重新部署。`email_test_mode: true` 表示使用 Resend 测试发件地址，受测试收件人限制。

健康接口仅检查配置是否存在，不验证密钥有效性或邮件投递。注册接口只有在 Resend 返回成功状态和邮件 ID 后才进入验证码步骤。最终投递请在 Resend 邮件日志中检查；接收成功不保证进入收件箱。

## 三页前端

- `/#/login`、`/#/register`：登录、注册和邮箱验证码。
- `/#/chat`：侧边栏、聊天记录、消息输入和情绪提示。
- `/#/settings`：账户信息、此浏览器的显示称呼与 Enter 发送偏好、最近 50 条消息导出、清空记录和退出。

聊天与设置需要登录。当前后端保留一条连续对话，“开始新的对话”会先确认删除已有记录，不提供多个独立会话。三个页面使用 hash 路由，无需修改 Render 路由规则。
