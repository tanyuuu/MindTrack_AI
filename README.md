# MindTrack AI — OpenAI + 账号系统联网版

已实现：

- 用户注册 / 登录 / 退出
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
- 邮箱验证
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
