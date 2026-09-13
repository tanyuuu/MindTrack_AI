
const messages=document.getElementById("messages"),form=document.getElementById("chatForm"),input=document.getElementById("chatInput"),typing=document.getElementById("typing"),modeLabel=document.getElementById("modeLabel"),sentimentBadge=document.getElementById("sentimentBadge"),clearChat=document.getElementById("clearChat");
const authModal=document.getElementById("authModal"),authForm=document.getElementById("authForm"),authTitle=document.getElementById("authTitle"),authSubtitle=document.getElementById("authSubtitle"),authEmail=document.getElementById("authEmail"),authPassword=document.getElementById("authPassword"),authSubmit=document.getElementById("authSubmit"),authError=document.getElementById("authError"),authSwitchText=document.getElementById("authSwitchText"),authSwitchBtn=document.getElementById("authSwitchBtn"),chatAuthGate=document.getElementById("chatAuthGate"),userMenu=document.getElementById("userMenu"),userEmail=document.getElementById("userEmail"),loginOpen=document.getElementById("loginOpen"),registerOpen=document.getElementById("registerOpen"),gateLogin=document.getElementById("gateLogin"),gateRegister=document.getElementById("gateRegister"),logoutBtn=document.getElementById("logoutBtn");
let authRequestVersion=0;
let authMode="login",token=localStorage.getItem("mindtrack_token")||"",currentUser=null,apiOnline=false;
const starter=messages.innerHTML;

async function detectApi(){try{const r=await fetch("/api/health",{signal:AbortSignal.timeout(90000)});apiOnline=r.ok}catch{apiOnline=false}}
async function apiFetch(url,options={}){const h=new Headers(options.headers||{});if(token)h.set("Authorization",`Bearer ${token}`);return fetch(url,{...options,headers:h})}
async function loadMe(){try{const r=await apiFetch("/api/auth/me");if(r.status===401){token="";currentUser=null;localStorage.removeItem("mindtrack_token");return}if(!r.ok)return;currentUser=await r.json()}catch{apiOnline=false}}
async function init(){await detectApi();if(token)await loadMe();updateAuthUI()}
function updateAuthUI(){const ok=!!(currentUser&&token);chatAuthGate.hidden=ok;loginOpen.hidden=ok;registerOpen.hidden=ok;userMenu.hidden=!ok;if(ok){userEmail.textContent=currentUser.email;modeLabel.textContent=apiOnline?"OpenAI 联网模式":"服务器未连接";loadHistory()}else{modeLabel.textContent=apiOnline?"请先登录":"服务器未连接";messages.innerHTML=starter}}
function openAuth(mode){authRequestVersion++;authSubmit.disabled=false;authForm.hidden=false;verificationPanel.hidden=true;verificationCode.value="";pendingVerificationEmail="";authPassword.autocomplete=mode==="register"?"new-password":"current-password";authMode=mode;authError.hidden=true;authPassword.value="";authModal.hidden=false;if(mode==="register"){authTitle.textContent="创建账号";authSubtitle.textContent="注册后即可使用联网 OpenAI 对话。";authSubmit.textContent="创建账号";authSwitchText.textContent="已经有账号？";authSwitchBtn.textContent="登录"}else{authTitle.textContent="登录";authSubtitle.textContent="登录后继续你的 MindTrack 对话。";authSubmit.textContent="登录";authSwitchText.textContent="还没有账号？";authSwitchBtn.textContent="立即注册"}setTimeout(()=>authEmail.focus(),30)}
function closeAuth(){authRequestVersion++;authSubmit.disabled=false;authModal.hidden=true}
function showErr(t){authError.textContent=t;authError.hidden=false}
loginOpen.onclick=()=>openAuth("login");registerOpen.onclick=()=>openAuth("register");gateLogin.onclick=()=>openAuth("login");gateRegister.onclick=()=>openAuth("register");document.querySelectorAll("[data-close-auth]").forEach(x=>x.onclick=closeAuth);authSwitchBtn.onclick=()=>openAuth(authMode==="login"?"register":"login");
authForm.onsubmit=async e=>{e.preventDefault();if(authSubmit.disabled)return;const requestVersion=++authRequestVersion;authSubmit.disabled=true;authSubmit.textContent="正在连接服务器…";authError.hidden=true;try{const r=await fetch(`/api/auth/${authMode}`,{method:"POST",headers:{"Content-Type":"application/json"},signal:AbortSignal.timeout(90000),body:JSON.stringify({email:authEmail.value.trim(),password:authPassword.value})});const d=await r.json().catch(()=>({detail:"服务器正在启动或暂时不可用，请稍后重试"}));if(requestVersion!==authRequestVersion)return;if(!r.ok)throw new Error(typeof d.detail==="string"?d.detail:"请检查邮箱和密码格式");apiOnline=true;if(d.verification_required){pendingVerificationEmail=d.email;verificationEmail.textContent=d.email;authForm.hidden=true;verificationPanel.hidden=false;authTitle.textContent="验证邮箱";authSubtitle.textContent="请输入邮件中的六位验证码（10 分钟内有效）。未收到或已过期？等待 60 秒后重新注册。";authError.hidden=true;verificationCode.focus();return}finishAuth(d)}catch(err){if(requestVersion===authRequestVersion)showErr(err.message)}finally{if(requestVersion===authRequestVersion){authSubmit.disabled=false;authSubmit.textContent=authMode==="login"?"登录":"创建账号"}}}
logoutBtn.onclick=async()=>{try{await apiFetch("/api/auth/logout",{method:"POST"})}catch{}token="";currentUser=null;localStorage.removeItem("mindtrack_token");messages.innerHTML=starter;updateAuthUI()}
async function loadHistory(){try{const r=await apiFetch("/api/history");if(!r.ok)return;const d=await r.json();messages.innerHTML=starter;(d.messages||[]).forEach(m=>addMessage(m.content,m.role==="user"?"user":"bot",false))}catch{}}
document.querySelectorAll(".prompt-chip").forEach(ch=>ch.onclick=()=>{if(!currentUser){openAuth("register");return}input.value=ch.textContent.trim();input.focus();document.getElementById("chat").scrollIntoView({behavior:"smooth"})});
clearChat.onclick=async()=>{if(!currentUser)return;await apiFetch("/api/history",{method:"DELETE"});messages.innerHTML=starter;sentimentBadge.textContent="情绪：中性"};
input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();form.requestSubmit()}});
form.onsubmit=async e=>{e.preventDefault();if(!currentUser){openAuth("login");return}const text=input.value.trim();if(!text)return;addMessage(text,"user");input.value="";typing.hidden=false;try{const r=await apiFetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:text})});const d=await r.json();if(!r.ok)throw new Error(d.detail||"AI 服务暂时不可用");sentimentBadge.textContent=`情绪：${d.sentiment||"中性"}`;addMessage(d.reply,"bot")}catch(err){addMessage(`暂时无法连接 AI：${err.message}`,"bot")}finally{typing.hidden=true}};
function addMessage(text,role,scroll=true){const w=document.createElement("div");w.className=`message ${role==="user"?"user-msg":"bot-msg"}`;w.innerHTML=role==="user"?`<div class="msg-body"><div class="msg-bubble"></div><time>现在</time></div>`:`<div class="avatar">M</div><div class="msg-body"><div class="msg-bubble"></div><time>现在</time></div>`;w.querySelector(".msg-bubble").textContent=text;messages.appendChild(w);if(scroll)requestAnimationFrame(()=>messages.scrollTop=messages.scrollHeight)}
init();
window.addEventListener(
    "load",
    initGoogleLogin
);

const verificationPanel =
    document.getElementById(
        "verificationPanel"
    );

const verificationForm =
    document.getElementById(
        "verificationForm"
    );

const verificationCode =
    document.getElementById(
        "verificationCode"
    );

const verificationEmail =
    document.getElementById(
        "verificationEmail"
    );

let pendingVerificationEmail = "";

function finishAuth(data) {
    if (!data.token || !data.user) throw new Error("登录响应无效，请重试");
    token = data.token;
    currentUser = data.user;
    localStorage.setItem("mindtrack_token", token);
    closeAuth();
    updateAuthUI();
}

verificationForm.addEventListener("submit", async event => {
    event.preventDefault();
    const button = verificationForm.querySelector("button");
    button.disabled = true;
    authError.hidden = true;
    try {
        const response = await fetch("/api/auth/verify", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({email: pendingVerificationEmail, code: verificationCode.value.trim()})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请输入六位数字验证码");
        finishAuth(data);
    } catch (error) {
        showErr(error.message);
    } finally {
        button.disabled = false;
    }
});

async function initGoogleLogin() {

    try {

        const response =
            await fetch(
                "/api/config"
            );

        const config =
            await response.json();

        if (
            !config.google_login_enabled
        ) {
            return;
        }

        if (!window.google) {

            setTimeout(
                initGoogleLogin,
                300
            );

            return;
        }

        google.accounts.id.initialize({

            client_id:
                config.google_client_id,

            callback:
                handleGoogleLogin
        });

        google.accounts.id.renderButton(

            document.getElementById(
                "googleLoginButton"
            ),

            {
                theme: "outline",
                size: "large",
                shape: "pill",
                text: "continue_with"
            }
        );

    } catch (error) {

        console.error(
            "Google login init error",
            error
        );
    }
}

async function handleGoogleLogin(
    response
) {

    try {

        const apiResponse =
            await fetch(
                "/api/auth/google",

                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            credential:
                                response
                                .credential
                        })
                }
            );

        const data =
            await apiResponse.json();

        if (!apiResponse.ok) {

            throw new Error(
                data.detail ||
                "Google 登录失败"
            );
        }

        token =
            data.token;

        currentUser =
            data.user;

        localStorage.setItem(
            "mindtrack_token",
            token
        );

        closeAuth();

        updateAuthUI();

    } catch (error) {

        showErr(
            error.message
        );
    }
}