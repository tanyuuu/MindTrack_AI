import os, hmac, time, base64, hashlib, secrets, sqlite3
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from openai import OpenAI

import requests
import logging
from dotenv import load_dotenv


from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

BASE_DIR=Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)
logger = logging.getLogger(__name__)
DB_PATH=Path(os.getenv("DB_PATH", "mindtrack.db").strip() or "mindtrack.db").expanduser()
if not DB_PATH.is_absolute():
    DB_PATH=BASE_DIR/DB_PATH
GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID", "").strip()
RESEND_API_KEY=os.getenv("RESEND_API_KEY", "").strip()
EMAIL_FROM=os.getenv("EMAIL_FROM", "").strip()
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY","").strip()
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-5.6-luna").strip()

app=FastAPI(title="MindTrack AI",version="2.0.0")
app.add_middleware(CORSMiddleware,allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])

SYSTEM_PROMPT="""You are MindTrack AI, a supportive mental wellness conversation assistant.
Reply in the same language as the user. Be warm, concise, practical, and non-judgmental.
You may help users reflect on emotions and stressors, suggest low-risk wellness practices such as journaling, breathing, grounding, rest, routines, and seeking social support, and help break problems into manageable steps.
Do not diagnose mental-health disorders, claim to be a doctor or therapist, recommend starting/stopping/changing prescription medication, or present yourself as emergency support.
If symptoms are persistent, severe, or significantly affect daily life, encourage professional support.
If a user appears to be in imminent danger or at risk of self-harm, encourage immediate contact with local emergency services, a crisis hotline, or a trusted person nearby. Focus on immediate safety.
This is a prototype mental wellness assistant, not medical care."""

CRISIS_TERMS=["自杀","轻生","不想活","结束生命","伤害自己","自残","suicide","kill myself","end my life","self harm","self-harm"]
NEGATIVE_TERMS=["焦虑","压力","难过","痛苦","疲惫","崩溃","失眠","害怕","孤独","生气","烦","担心","低落"]
POSITIVE_TERMS=["开心","轻松","不错","很好","平静","感谢","希望","进步","舒服","放松"]

class AuthRequest(BaseModel):
    email:EmailStr
    password:str=Field(min_length=8,max_length=128)
class ChatRequest(BaseModel):
    message:str=Field(min_length=1,max_length=2000)

def db():
    con=sqlite3.connect(DB_PATH);con.row_factory=sqlite3.Row;return con
def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at INTEGER NOT NULL);
        """)
init_db()

def migrate_db():
    with db() as con:

        columns = {
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        }

        if "verified" not in columns:
            con.execute("""
                ALTER TABLE users
                ADD COLUMN verified INTEGER
                NOT NULL DEFAULT 0
            """)

        if "google_sub" not in columns:
            con.execute("""
                ALTER TABLE users
                ADD COLUMN google_sub TEXT
            """)

        if "auth_provider" not in columns:
            con.execute("""
                ALTER TABLE users
                ADD COLUMN auth_provider TEXT
                NOT NULL DEFAULT 'email'
            """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS
            verification_codes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                code TEXT NOT NULL,

                expires_at INTEGER NOT NULL,

                created_at INTEGER NOT NULL
            )
        """)

migrate_db()
with db() as con:
    if "attempts" not in {r["name"] for r in con.execute("PRAGMA table_info(verification_codes)")}:
        con.execute("ALTER TABLE verification_codes ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")

class EmailDeliveryError(RuntimeError):
    """Contains only a safe, application-authored message for the user."""


def generate_verification_code():
    return f"{secrets.randbelow(1000000):06d}"


def send_verification_email(to_email: str, code: str):
    if not RESEND_API_KEY or not EMAIL_FROM:
        raise EmailDeliveryError("服务器未配置邮件服务：请设置 RESEND_API_KEY 和 EMAIL_FROM，然后重启或重新部署")

    html = f"""
    <html>
        <body style="
            background:#f4f7f5;
            padding:40px;
            font-family:Arial,sans-serif;
        ">

            <div style="
                max-width:480px;
                margin:auto;
                background:white;
                border-radius:20px;
                padding:36px;
            ">

                <h2>
                    MindTrack AI
                </h2>

                <p>
                    欢迎注册 MindTrack。
                </p>

                <p>
                    你的验证码是：
                </p>

                <div style="
                    font-size:34px;
                    font-weight:bold;
                    color:#1d6b4b;
                    letter-spacing:8px;
                    margin:28px 0;
                ">
                    {code}
                </div>

                <p>
                    验证码 10 分钟内有效。
                </p>

            </div>

        </body>
    </html>
    """

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "MindTrack/2.0",
            },
            json={
                "from": EMAIL_FROM,
                "to": [to_email],
                "subject": "MindTrack AI 验证码",
                "html": html,
                "text": f"你的 MindTrack AI 验证码是：{code}。10 分钟内有效。",
            },
            timeout=(5, 15),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise EmailDeliveryError("无法连接邮件 API 或请求超时，请稍后重试") from None

    # Never expose provider response bodies, credentials, or recipient details.
    if not 200 <= response.status_code < 300:
        logger.warning("Resend email rejected (HTTP %s)", response.status_code)
        if response.status_code == 401:
            detail = "邮件服务认证失败，请检查 RESEND_API_KEY 后重新部署"
        elif response.status_code == 403 and "onboarding@resend.dev" in EMAIL_FROM.lower():
            detail = "Resend 拒绝发送：当前使用测试发件地址，只能发给注册 Resend 账号时的邮箱；如需发给其他人，请验证自己的发件域名。也请确认 API Key 有发信权限"
        elif response.status_code in (400, 403, 422):
            detail = "邮件服务拒绝发送，请检查 API Key 权限、EMAIL_FROM 的域名验证和测试收件人限制"
        elif response.status_code == 429:
            detail = "邮件服务发送过于频繁或额度不足，请稍后重试或检查 Resend 配额"
        else:
            detail = "邮件服务暂时不可用，请稍后重试"
        raise EmailDeliveryError(detail)
    try:
        data = response.json()
    except ValueError:
        raise EmailDeliveryError("邮件服务返回了无效响应，请稍后重试") from None
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not data["id"]:
        raise EmailDeliveryError("邮件服务未确认发送，请稍后重试")
    logger.info("Resend accepted verification email")
    return data["id"]

# add verification code api
class VerifyRequest(BaseModel):

    email: EmailStr

    code: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^[0-9]{6}$"
    )

@app.post("/api/auth/verify")
def verify_email(req: VerifyRequest):
    email = req.email.lower().strip()
    error = None
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        user = con.execute("SELECT id,email,verified FROM users WHERE email=?", (email,)).fetchone()
        if not user or user["verified"]:
            raise HTTPException(400, "请重新注册获取验证码，或登录已验证的账号")
        record = con.execute("SELECT * FROM verification_codes WHERE user_id=? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
        if not record or record["expires_at"] <= int(time.time()):
            raise HTTPException(400, "验证码不存在或已经过期，请重新注册获取验证码")
        if record["attempts"] >= 5:
            raise HTTPException(429, "验证码尝试次数过多，请重新注册获取验证码")
        if not hmac.compare_digest(record["code"], req.code):
            con.execute("UPDATE verification_codes SET attempts=attempts+1 WHERE id=?", (record["id"],))
            error = "验证码不正确"
        else:
            con.execute("UPDATE users SET verified=1 WHERE id=?", (user["id"],))
            con.execute("DELETE FROM verification_codes WHERE user_id=?", (user["id"],))
    if error:
        raise HTTPException(400, error)
    return {"token": new_session(user["id"]), "user": {"id": user["id"], "email": email}}

def password_hash(password):
    salt=secrets.token_bytes(16);iters=310000
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,iters)
    return f"pbkdf2_sha256${iters}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"
def password_verify(password,stored):
    try:
        scheme,iters,salt_b64,digest_b64=stored.split("$")
        salt=base64.b64decode(salt_b64);expected=base64.b64decode(digest_b64)
        actual=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,int(iters))
        return scheme=="pbkdf2_sha256" and hmac.compare_digest(actual,expected)
    except Exception:return False
def new_session(uid):
    token=secrets.token_urlsafe(32);th=hashlib.sha256(token.encode()).hexdigest();exp=int(time.time())+2592000
    with db() as con:
        con.execute("DELETE FROM sessions WHERE expires_at<?",(int(time.time()),))
        con.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",(th,uid,exp))
    return token
def bearer(authorization:Optional[str]=Header(None)):
    if not authorization or not authorization.startswith("Bearer "):raise HTTPException(401,"请先登录")
    return authorization[7:].strip()
def current_user(token:str=Depends(bearer)):
    th=hashlib.sha256(token.encode()).hexdigest()
    with db() as con:
        row=con.execute("SELECT u.id,u.email FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.verified=1",(th,int(time.time()))).fetchone()
    if not row:raise HTTPException(401,"登录已过期，请重新登录")
    return {"id":row["id"],"email":row["email"],"token_hash":th}
def sentiment(text):
    neg=sum(w in text for w in NEGATIVE_TERMS);pos=sum(w in text for w in POSITIVE_TERMS)
    return "压力/低落" if neg>pos else ("积极" if pos>neg else "中性")
def save(uid,role,content):
    with db() as con:con.execute("INSERT INTO messages(user_id,role,content,created_at) VALUES(?,?,?,?)",(uid,role,content,int(time.time())))
def recent(uid,limit=12):
    with db() as con:rows=con.execute("SELECT role,content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",(uid,limit)).fetchall()
    return [{"role":r["role"],"content":r["content"]} for r in reversed(rows)]

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL if OPENAI_API_KEY else None,
        "email_provider": "resend",
        "email_configured": bool(RESEND_API_KEY and EMAIL_FROM),
        "email_test_mode": "onboarding@resend.dev" in EMAIL_FROM.lower(),
    }

@app.get("/api/config")
def config():

    return {
        "google_client_id":
            GOOGLE_CLIENT_ID,

        "google_login_enabled":
            bool(GOOGLE_CLIENT_ID)
    }

# modify register api
@app.post("/api/auth/register")
def register(req: AuthRequest):
    email = req.email.lower().strip()
    now = int(time.time())
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        existing = con.execute("SELECT id,verified FROM users WHERE email=?", (email,)).fetchone()
        if existing and existing["verified"]:
            raise HTTPException(409, "这个邮箱已经注册")
        if existing:
            latest = con.execute("SELECT created_at FROM verification_codes WHERE user_id=? ORDER BY id DESC LIMIT 1", (existing["id"],)).fetchone()
            if latest and latest["created_at"] > now - 60:
                raise HTTPException(429, "请等待 60 秒后再发送验证码")
            user_id = existing["id"]
            con.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(req.password), user_id))
        else:
            cursor = con.execute("INSERT INTO users(email,password_hash,verified,auth_provider,created_at) VALUES(?,?,0,'email',?)", (email, password_hash(req.password), now))
            user_id = cursor.lastrowid
        code = generate_verification_code()
        con.execute("DELETE FROM verification_codes WHERE user_id=?", (user_id,))
        con.execute("INSERT INTO verification_codes(user_id,code,expires_at,created_at) VALUES(?,?,?,?)", (user_id, code, now + 600, now))
        # Roll back account/password/code changes if delivery fails.
        try:
            send_verification_email(email, code)
        except Exception as exc:
            logger.warning("Verification email failed (%s)", type(exc).__name__)
            detail = str(exc) if isinstance(exc, EmailDeliveryError) else "验证码邮件发送失败，请稍后重试"
            raise HTTPException(503, detail) from None
    return {"verification_required": True, "email": email}

# google login api
class GoogleLoginRequest(BaseModel):
    credential: str

@app.post("/api/auth/google")
def google_login(
    req: GoogleLoginRequest
):

    if not GOOGLE_CLIENT_ID:

        raise HTTPException(
            500,
            "Google 登录尚未配置"
        )

    try:

        google_user = (
            id_token
            .verify_oauth2_token(
                req.credential,

                google_requests
                .Request(),

                GOOGLE_CLIENT_ID
            )
        )

    except Exception:

        raise HTTPException(
            401,
            "Google 身份验证失败"
        )

    email = google_user.get(
        "email"
    )

    google_sub = google_user.get(
        "sub"
    )

    verified = google_user.get(
        "email_verified",
        False
    )

    if not verified:

        raise HTTPException(
            403,
            "Google 邮箱未验证"
        )

    if not email:

        raise HTTPException(
            400,
            "无法读取 Google 邮箱"
        )

    email = email.lower()

    with db() as con:

        user = con.execute("""
            SELECT id,email,verified

            FROM users

            WHERE email=?
        """, (
            email,
        )).fetchone()

        if user:

            user_id = user["id"]
            # Discard an unverified password when Google proves ownership.
            if not user["verified"]:
                con.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(secrets.token_urlsafe(32)), user_id))
            con.execute("DELETE FROM verification_codes WHERE user_id=?", (user_id,))

            con.execute("""
                UPDATE users

                SET
                    verified=1,
                    google_sub=?,
                    auth_provider='google'

                WHERE id=?
            """, (
                google_sub,
                user_id
            ))

        else:

            temporary_password = (
                secrets
                .token_urlsafe(32)
            )

            cursor = con.execute("""
                INSERT INTO users(
                    email,
                    password_hash,
                    verified,
                    google_sub,
                    auth_provider,
                    created_at
                )

                VALUES(
                    ?, ?, ?, ?, ?, ?
                )
            """, (
                email,

                password_hash(
                    temporary_password
                ),

                1,

                google_sub,

                "google",

                int(time.time())
            ))

            user_id = (
                cursor.lastrowid
            )

    token = new_session(
        user_id
    )

    return {
        "token": token,

        "user": {
            "id": user_id,
            "email": email
        }
    }

@app.post("/api/auth/login")
def login(req:AuthRequest):
    email=req.email.lower().strip()
    with db() as con:
        row=con.execute("""
            SELECT
                id,
                email,
                password_hash,
                verified,
                auth_provider
            FROM users
            WHERE email=?
        """,(email,)).fetchone()
    if not row or not password_verify(req.password,row["password_hash"]):raise HTTPException(401,"邮箱或密码不正确")
    if not row["verified"]:raise HTTPException(403,"请先验证邮箱；如验证码已过期，请重新注册获取验证码")
    return {"token":new_session(row["id"]),"user":{"id":row["id"],"email":row["email"]}}

@app.get("/api/auth/me")
def me(user=Depends(current_user)):return {"id":user["id"],"email":user["email"]}

@app.post("/api/auth/logout")
def logout(user=Depends(current_user)):
    with db() as con:con.execute("DELETE FROM sessions WHERE token_hash=?",(user["token_hash"],))
    return {"ok":True}

@app.get("/api/history")
def history(user=Depends(current_user)):return {"messages":recent(user["id"],50)}

@app.delete("/api/history")
def clear_history(user=Depends(current_user)):
    with db() as con:con.execute("DELETE FROM messages WHERE user_id=?",(user["id"],))
    return {"ok":True}

@app.post("/api/chat")
def chat(req:ChatRequest,user=Depends(current_user)):
    text=req.message.strip();save(user["id"],"user",text)
    lower=text.lower()
    if any(t.lower() in lower for t in CRISIS_TERMS):
        reply="我很在意你刚刚提到的内容。如果你现在可能会伤害自己或处于即时危险中，请立即联系你所在地区的紧急服务或危机热线，并尽快去到一个可信任的人身边。不要独自面对这一刻。你可以告诉我：你现在是否处在立即危险中？"
        save(user["id"],"assistant",reply)
        return {"reply":reply,"sentiment":sentiment(text)}
    if not OPENAI_API_KEY:raise HTTPException(503,"服务器还没有配置 OPENAI_API_KEY。请在服务器环境变量中设置后重启服务。")
    items=[{"role":"developer","content":SYSTEM_PROMPT}]+recent(user["id"],12)
    try:
        client=OpenAI(api_key=OPENAI_API_KEY)
        response=client.responses.create(model=OPENAI_MODEL,input=items,max_output_tokens=500)
        reply=(response.output_text or "").strip()
        if not reply:raise RuntimeError("empty response")
    except Exception as exc:
        logger.warning("OpenAI API failed (%s)", type(exc).__name__)
        raise HTTPException(502,"OpenAI 服务暂时不可用，请稍后再试")
    save(user["id"],"assistant",reply)
    return {"reply":reply,"sentiment":sentiment(text)}

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "index.html")

@app.get("/{asset}", include_in_schema=False)
def static_asset(asset: str):
    if asset not in {"app.js", "styles.css"}:
        raise HTTPException(404, "Not found")
    return FileResponse(BASE_DIR / asset)
