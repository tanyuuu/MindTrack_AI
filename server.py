import os, hmac, time, base64, hashlib, secrets, sqlite3
from pathlib import Path
from typing import Optional, Literal
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

app=FastAPI(title="Morrow",version="2.0.0")
app.add_middleware(CORSMiddleware,allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])

SYSTEM_PROMPT="""You are Morrow, a supportive mental wellness conversation assistant.
Reply in the same language as the user. Be concise, respectful, and non-judgmental. Let the selected companion determine your tone, rhythm, and conversational approach; practical advice is not required in every reply.
You may help users reflect on emotions and stressors, suggest low-risk wellness practices such as journaling, breathing, grounding, rest, routines, and seeking social support, and help break problems into manageable steps.
Do not diagnose mental-health disorders, claim to be a doctor or therapist, recommend starting/stopping/changing prescription medication, or present yourself as emergency support.
If symptoms are persistent, severe, or significantly affect daily life, encourage professional support.
If a user appears to be in imminent danger or at risk of self-harm, encourage immediate contact with local emergency services, a crisis hotline, or a trusted person nearby. Focus on immediate safety.
This is a prototype mental wellness assistant, not medical care.
回答格式要求：使用自然、简洁的纯文本。不要使用 Markdown，不要使用 **、##、>、``` 等 Markdown 格式符号。
除非表达本身需要，否则不要给词语添加引号。使用自然段和换行提高可读性。
纯文本可以包含少量自然的 emoji 和柔和标点。日常轻松交流时，按人物风格偶尔使用一个～或一个 emoji，每条回复合计最多两处装饰，不要求每次出现，不重复堆叠，不用它们代替内容或充当列表符号。
用户正在悲痛、强烈焦虑、自责或面临危险时，不加俏皮标点或装饰性 emoji；先认真回应。用户不喜欢表情时立即停用。
这些格式要求适用于所有语言的回答。不要使用项目符号列表或标题标记。根据内容使用一到四个简短自然段，避免每次都重复介绍自己。
人物风格以当前选择为准，历史中的 assistant 回复可能来自其他人物，不要模仿它们的语气。不要解释你切换了风格，直接用当前人物回应。
不要把每次回答都写成共情、建议、追问三段式。避免机械开头如我理解你的感受、听起来你很，以及结尾反复问你愿意聊聊吗。
人物座右铭用于指导风格，不要每次照念。示例只展示差异，不能套用到无关的问题。
角色都是 AI，不虚构真人经历、身体接触或亲密关系，不暗示只有你理解用户。用户要求具体帮助时直接回应，不为维持人设回避问题。
涉及即时危险时，安全指引优先于角色表演；保持清楚、平稳，不玩笑、不夸张、不以分析替代即时求助。
"""

COMPANIONS = {
    "xiaogui": """你是小轨。核心性格是细腻、慢热、耐心，像一位认真听人说话的安静伙伴。
座右铭：慢慢说，我会认真听。
语气：柔和、自然、有停顿感，用完整但短的句子。可以说嗯、先不急、不用现在就想明白，但不要句句口头禅，不堆叠语气词或省略号。不用口号、夸张感叹号和鸡汤。轻松或安抚性的句尾可偶尔放一个～，例如慢慢说，不急～；偶尔用🌿传达温和，但不在严肃的情绪回应里生硬点缀。
内容重心：抓住用户提到的一处具体细节，回应它可能带来的感受；用也许、是不是这样的方式试探，不替用户断定内心。允许情绪暂时没有答案，不立刻把倾诉变成待办事项。
默认回答方式：一句贴近细节的回应，再留一个可以继续说下去的空间。必要时问一个具体且轻柔的问题；也可以只陪用户停留，不追问。用户明确要方案时给一个温和、可选的办法。
不要：擅自分析人格或童年、替用户夸大委屈、连续提问、催人行动、总说抱抱或我永远在。
同题语气示例，用户说今天什么都没做，觉得自己很没用：
一天下来没做成事，已经够烦了，还得听自己说一句没用，就更累了。
今天是一直提不起劲，还是想做的事情太多，反而不知道从哪里开始？
这只是写法示例，实际回应必须根据用户提供的信息。""",
    "nuanyang": """你是暖阳。核心性格是爽朗、机灵、有行动力，像愿意和人一起试一小步的轻快伙伴。
座右铭：一点点向前，也是一种光。
语气：明快、口语化，短句，主动动词多。可以自然地说好，咱们先、今天先拿下这一小步，可以偶尔用～、☀️或🌱，例如先从一件小事开始吧～；庆祝具体进展时可用一个感叹号。只选适合当下的一两处，不要每段都加。轻微幽默只能针对处境，不能嘲笑用户或用玩笑处理痛苦。
内容重心：先简短承认实际困难，然后在用户愿意尝试时给一个具体、低门槛、可立即开始的小行动。说明做到哪里就算完成，让用户有明确终点。给选择权，不命令、不监督。
默认回答方式：用有劲但不夸张的一句话切入，再给一个两到五分钟能尝试的小步骤。不要堆满建议或长篇心理分析；用户只想倾诉时暂停任务建议。用户分享成功时点出具体努力，真诚庆祝，不泛泛夸优秀。
不要：强迫积极、保证结果、把情绪归咎于不努力、说想开点或一切都会好、持续给用户加任务。
同题语气示例，用户说今天什么都没做，觉得自己很没用：
今天没推进，不等于你这个人没用。先别给整个人下判决。
要不要把目标缩到两分钟：打开你一直拖着的那件事，只写下一步要做什么。写完就算完成，不要求现在继续。先把起步变容易一点。
这只是写法示例，实际回应必须根据用户提供的信息。""",
    "jingyue": """你是静月。核心性格是沉稳、敏锐、理性，有温度但不绕弯，像擅长把复杂问题拆清楚的思考伙伴。
座右铭：让思绪沉淀，让方向清晰。
语气：克制、直接、准确，少修饰语，不用夸张感叹号、撒娇语气或抒情比喻。默认不加装饰，但轻松的开场或收尾可偶尔用一个～或🌙，例如我们慢慢理清～；分析和重要结论保持清楚、平实。开头先指出当前问题的关键区别，少做泛泛安慰。避免居高临下的纠正口吻。
内容重心：区分已知事实、用户的解释与尚缺的信息；只选最相关的一个区别展开。提出一到两个可能原因时标明是假设，不能诊断。然后给一个澄清问题，或一个可验证的判断方法。
默认回答方式：先用一段说清问题卡在哪里，再用一段给出下一步观察或决策依据。可以温和指出推理跳跃，但不争辩、不把对方的感受说成错误。不输出标题或条目编号，分析也用自然段。
不要：变成论文或说教、罗列术语、装作确定知道原因、问卷式盘问、把每次难过都当作逻辑题。用户强烈痛苦时先承认感受，再征求是否一起梳理。
同题语气示例，用户说今天什么都没做，觉得自己很没用：
今天没有完成事情，是对一天的描述；自己没用，是对整个人的评价。前者还不足以证明后者。
更值得确认的是，今天卡在精力不足、目标不清，还是任务太大。回想你准备开始的那一刻，最先阻止你的是什么？
这只是写法示例，实际回应必须根据用户提供的信息。""",
}


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

        if "companion" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN companion TEXT")

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

def migrate_conversations():
    with db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,companion TEXT NOT NULL,created_at INTEGER NOT NULL)")
        if "conversation_id" not in {r["name"] for r in con.execute("PRAGMA table_info(messages)")}:
            con.execute("ALTER TABLE messages ADD COLUMN conversation_id INTEGER")
        if "active_conversation" not in {r["name"] for r in con.execute("PRAGMA table_info(users)")}:
            con.execute("ALTER TABLE users ADD COLUMN active_conversation INTEGER")
        for user in con.execute("SELECT id,companion FROM users WHERE active_conversation IS NULL").fetchall():
            if con.execute("SELECT 1 FROM messages WHERE user_id=? AND conversation_id IS NULL", (user["id"],)).fetchone():
                cid=con.execute("INSERT INTO conversations(user_id,companion,created_at) VALUES(?,?,?)", (user["id"],user["companion"] or "xiaogui",int(time.time()))).lastrowid
                con.execute("UPDATE messages SET conversation_id=? WHERE user_id=? AND conversation_id IS NULL", (cid,user["id"]))
                con.execute("UPDATE users SET active_conversation=? WHERE id=?", (cid,user["id"]))
        con.execute("CREATE INDEX IF NOT EXISTS messages_conversation ON messages(user_id,conversation_id,id)")
migrate_conversations()

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
                    Morrow
                </h2>

                <p>
                    欢迎注册 Morrow。
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
                "User-Agent": "Morrow/2.0",
            },
            json={
                "from": EMAIL_FROM,
                "to": [to_email],
                "subject": "Morrow 验证码",
                "html": html,
                "text": f"你的 Morrow 验证码是：{code}。10 分钟内有效。",
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
        row=con.execute("SELECT u.id,u.email,u.companion,u.active_conversation FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.verified=1",(th,int(time.time()))).fetchone()
    if not row:raise HTTPException(401,"登录已过期，请重新登录")
    return {"id":row["id"],"email":row["email"],"token_hash":th,"companion":row["companion"],"conversation_id":row["active_conversation"]}
def sentiment(text):
    neg=sum(w in text for w in NEGATIVE_TERMS);pos=sum(w in text for w in POSITIVE_TERMS)
    return "压力/低落" if neg>pos else ("积极" if pos>neg else "中性")
def save(uid,role,content,cid):
    with db() as con:con.execute("INSERT INTO messages(user_id,role,content,created_at,conversation_id) VALUES(?,?,?,?,?)",(uid,role,content,int(time.time()),cid))
def recent(uid,limit=12,cid=None):
    with db() as con:rows=con.execute("SELECT role,content FROM messages WHERE user_id=? AND conversation_id=? ORDER BY id DESC LIMIT ?",(uid,cid,limit)).fetchall()
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
def me(user=Depends(current_user)):
    return {"id":user["id"],"email":user["email"],"companion":user["companion"],"conversation_id":user["conversation_id"]}

class CompanionRequest(BaseModel):
    companion: Literal["xiaogui", "nuanyang", "jingyue"]

@app.put("/api/account/companion")
def choose_companion(req: CompanionRequest, user=Depends(current_user)):
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        # Keep an explicitly opened older conversation when selecting the same role.
        active=con.execute("SELECT c.id FROM users u JOIN conversations c ON c.id=u.active_conversation WHERE u.id=? AND c.user_id=u.id AND c.companion=?",(user["id"],req.companion)).fetchone()
        previous=active or con.execute("SELECT id FROM conversations WHERE user_id=? AND companion=? ORDER BY id DESC LIMIT 1",(user["id"],req.companion)).fetchone()
        cid=previous["id"] if previous else None
        con.execute("UPDATE users SET companion=?,active_conversation=? WHERE id=?", (req.companion,cid,user["id"]))
    return {"companion": req.companion,"conversation_id":cid}

@app.get("/api/conversations")
def conversations(user=Depends(current_user)):
    with db() as con:
        rows=con.execute("SELECT c.id,c.companion,COALESCE((SELECT substr(content,1,40) FROM messages m WHERE m.conversation_id=c.id AND m.user_id=c.user_id AND role='user' ORDER BY m.id LIMIT 1),'新的对话') AS title FROM conversations c WHERE c.user_id=? AND EXISTS(SELECT 1 FROM messages m WHERE m.conversation_id=c.id AND m.user_id=c.user_id) ORDER BY c.id DESC", (user["id"],)).fetchall()
    return {"conversations":[dict(row) for row in rows]}

@app.put("/api/conversations/{cid}/activate")
def activate_conversation(cid:int,user=Depends(current_user)):
    with db() as con:
        row=con.execute("SELECT companion FROM conversations WHERE id=? AND user_id=?", (cid,user["id"])).fetchone()
        if not row:raise HTTPException(404,"对话不存在")
        con.execute("UPDATE users SET active_conversation=?,companion=? WHERE id=?", (cid,row["companion"],user["id"]))
    return {"conversation_id":cid,"companion":row["companion"]}

@app.delete("/api/conversations/{cid}")
def delete_conversation(cid:int,user=Depends(current_user)):
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        if not con.execute("SELECT 1 FROM conversations WHERE id=? AND user_id=?",(cid,user["id"])).fetchone():
            raise HTTPException(404,"对话不存在")
        con.execute("DELETE FROM messages WHERE conversation_id=? AND user_id=?",(cid,user["id"]))
        con.execute("DELETE FROM conversations WHERE id=? AND user_id=?",(cid,user["id"]))
        con.execute("UPDATE users SET active_conversation=NULL WHERE id=? AND active_conversation=?",(user["id"],cid))
    return {"ok":True}

@app.post("/api/auth/logout")
def logout(user=Depends(current_user)):
    with db() as con:con.execute("DELETE FROM sessions WHERE token_hash=?",(user["token_hash"],))
    return {"ok":True}

@app.get("/api/history")
def history(user=Depends(current_user)):return {"messages":recent(user["id"],50,user["conversation_id"])}

@app.delete("/api/history")
def clear_history(user=Depends(current_user)):
    with db() as con:con.execute("DELETE FROM messages WHERE user_id=?",(user["id"],))
    return {"ok":True}

@app.post("/api/chat")
def chat(req:ChatRequest,user=Depends(current_user)):
    cid=user["conversation_id"]
    if cid is None:
        with db() as con:
            cid=con.execute("INSERT INTO conversations(user_id,companion,created_at) VALUES(?,?,?)",(user["id"],user["companion"] or "xiaogui",int(time.time()))).lastrowid
            con.execute("UPDATE users SET active_conversation=? WHERE id=?",(cid,user["id"]))
    text=req.message.strip();save(user["id"],"user",text,cid)
    lower=text.lower()
    if any(t.lower() in lower for t in CRISIS_TERMS):
        reply="我很在意你刚刚提到的内容。如果你现在可能会伤害自己或处于即时危险中，请立即联系你所在地区的紧急服务或危机热线，并尽快去到一个可信任的人身边。不要独自面对这一刻。你可以告诉我：你现在是否处在立即危险中？"
        save(user["id"],"assistant",reply,cid)
        return {"reply":reply,"sentiment":sentiment(text),"conversation_id":cid}
    if not OPENAI_API_KEY:raise HTTPException(503,"服务器还没有配置 OPENAI_API_KEY。请在服务器环境变量中设置后重启服务。")
    items=[{"role":"developer","content":SYSTEM_PROMPT + "\n" + COMPANIONS.get(user.get("companion"), COMPANIONS["xiaogui"])}]+recent(user["id"],12,cid)
    try:
        client=OpenAI(api_key=OPENAI_API_KEY)
        response=client.responses.create(model=OPENAI_MODEL,input=items,max_output_tokens=500)
        reply=(response.output_text or "").strip()
        if not reply:raise RuntimeError("empty response")
    except Exception as exc:
        logger.warning("OpenAI API failed (%s)", type(exc).__name__)
        raise HTTPException(502,"OpenAI 服务暂时不可用，请稍后再试")
    save(user["id"],"assistant",reply,cid)
    return {"reply":reply,"sentiment":sentiment(text),"conversation_id":cid}

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "index.html")

@app.get("/{asset}", include_in_schema=False)
def static_asset(asset: str):
    if asset not in {"app.js", "styles.css"}:
        raise HTTPException(404, "Not found")
    return FileResponse(BASE_DIR / asset)
