import os, hmac, time, base64, hashlib, secrets, sqlite3
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from openai import OpenAI

BASE_DIR=Path(__file__).resolve().parent
DB_PATH=BASE_DIR/"mindtrack.db"
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY","").strip()
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-5.6-luna").strip()

app=FastAPI(title="MindTrack AI",version="2.0.0")
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","*").split(","),allow_credentials=False,allow_methods=["*"],allow_headers=["*"])

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
        row=con.execute("SELECT u.id,u.email FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",(th,int(time.time()))).fetchone()
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
    return {"status":"ok","openai_configured":bool(OPENAI_API_KEY),"model":OPENAI_MODEL if OPENAI_API_KEY else None}

@app.post("/api/auth/register")
def register(req:AuthRequest):
    email=req.email.lower().strip()
    with db() as con:
        if con.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone():raise HTTPException(409,"这个邮箱已经注册")
        cur=con.execute("INSERT INTO users(email,password_hash,created_at) VALUES(?,?,?)",(email,password_hash(req.password),int(time.time())))
        uid=cur.lastrowid
    return {"token":new_session(uid),"user":{"id":uid,"email":email}}

@app.post("/api/auth/login")
def login(req:AuthRequest):
    email=req.email.lower().strip()
    with db() as con:row=con.execute("SELECT id,email,password_hash FROM users WHERE email=?",(email,)).fetchone()
    if not row or not password_verify(req.password,row["password_hash"]):raise HTTPException(401,"邮箱或密码不正确")
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
        print(f"OpenAI API error: {type(exc).__name__}: {exc}")
        raise HTTPException(502,"OpenAI 服务暂时不可用，请稍后再试")
    save(user["id"],"assistant",reply)
    return {"reply":reply,"sentiment":sentiment(text)}

app.mount("/",StaticFiles(directory=str(BASE_DIR),html=True),name="site")
