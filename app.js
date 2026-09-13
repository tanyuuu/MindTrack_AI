'use strict';
const $ = id => document.getElementById(id);
const state = {token: localStorage.getItem('mindtrack_token') || '', user: null, mode: 'login', pendingEmail: '', pendingName: '', authVersion: 0, sessionVersion: 0, busy: false, historyReady: false};
function notice(id, message, error = false) {const node = $(id); node.textContent = message; node.hidden = !message; node.classList.toggle('error', error);}
function preferences() {try {return JSON.parse(localStorage.getItem(`mindtrack_prefs:${state.user?.email}`) || '{}');} catch {return {};}}
function savePreferences(values) {localStorage.setItem(`mindtrack_prefs:${state.user.email}`, JSON.stringify({...preferences(), ...values}));}
function label() {return preferences().name || state.user?.email.split('@')[0] || '我的账户';}
async function request(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (options.body) headers.set('Content-Type', 'application/json');
  let response;
  try {response = await fetch(url, {...options, headers, signal: options.signal || AbortSignal.timeout(90000)});}
  catch {throw new Error('连接暂时中断，服务器可能正在启动，请稍后重试。');}
  const data = await response.json().catch(() => ({detail: '服务器暂时不可用，请稍后重试。'}));
  if (!response.ok) {const error = new Error(typeof data.detail === 'string' ? data.detail : '请检查填写的邮箱、密码或验证码。'); error.status = response.status; throw error;}
  return data;
}
function closeSidebar() {$('sidebar').classList.remove('open'); $('sidebarBackdrop').hidden = true; $('menuToggle').setAttribute('aria-expanded', 'false');}
function route() {
  closeSidebar();
  const path = location.hash || '#/login';
  if (!state.user) {
    $('workspace').hidden = true; $('authPage').hidden = false;
    if (path !== '#/register' && path !== '#/login') {location.hash = '#/login'; return;}
    openAuth(path === '#/register' ? 'register' : 'login'); return;
  }
  if (path !== '#/settings' && path !== '#/chat') {location.hash = '#/chat'; return;}
  $('authPage').hidden = true; $('workspace').hidden = false;
  const settings = path === '#/settings';
  $('chatPage').hidden = settings; $('settingsPage').hidden = !settings;
  $('chatNav').classList.toggle('active', !settings);
  $('accountNav').setAttribute('aria-current', settings ? 'page' : 'false');
  $('pageLabel').textContent = settings ? 'Account / Settings' : '你的对话空间';
  updateProfile();
  if (!settings && !state.historyReady) loadHistory();
}
function openAuth(mode) {
  state.authVersion++; state.mode = mode; state.pendingEmail = ''; state.pendingName = '';
  $('authForm').hidden = false; $('verificationForm').hidden = true; $('authSwitch').hidden = false;
  $('authSubmit').disabled = false; $('verifySubmit').disabled = false; $('authPassword').value = ''; $('verificationCode').value = '';
  $('authPassword').type = 'password'; $('passwordToggle').textContent = '显示';
  const register = mode === 'register';
  $('nameLabel').hidden = !register;
  $('authPassword').autocomplete = register ? 'new-password' : 'current-password';
  $('authEyebrow').textContent = register ? 'START GENTLY' : 'WELCOME BACK';
  $('authTitle').textContent = register ? '留一点空间，给自己。' : '很高兴，再见到你。';
  $('authSubtitle').textContent = register ? '创建账号，从一次自在的对话开始。' : '登录，继续你的 MindTrack 对话。';
  $('authSubmit').textContent = register ? '创建账号 ↗' : '登录 ↗';
  $('authSwitchText').textContent = register ? '已经有账号？' : '还没有账号？';
  $('authSwitchLink').textContent = register ? '登录' : '创建账号';
  $('authSwitchLink').href = register ? '#/login' : '#/register';
  notice('authError', '');
}
async function finishAuth(data) {
  if (!data.token || !data.user?.email) throw new Error('登录响应无效，请重试。');
  state.authVersion++; state.sessionVersion++; state.token = data.token; state.user = data.user; state.historyReady = false;
  localStorage.setItem('mindtrack_token', state.token);
  if (state.pendingName) savePreferences({name: state.pendingName});
  state.pendingName = ''; state.pendingEmail = ''; $('authPassword').value = ''; $('verificationCode').value = '';
  location.hash = '#/chat'; route();
}
$('authForm').addEventListener('submit', async event => {
  event.preventDefault(); if ($('authSubmit').disabled) return;
  const version = ++state.authVersion; const mode = state.mode;
  $('authSubmit').disabled = true; $('authSubmit').textContent = '正在连接…'; notice('authError', '');
  try {
    const data = await request(`/api/auth/${mode}`, {method:'POST', body:JSON.stringify({email:$('authEmail').value.trim(), password:$('authPassword').value})});
    if (version !== state.authVersion) return;
    if (data.verification_required) {
      state.pendingEmail = data.email; state.pendingName = $('authName').value.trim();
      $('authForm').hidden = true; $('verificationForm').hidden = false; $('authSwitch').hidden = true;
      $('verificationEmail').textContent = data.email; $('authTitle').textContent = '只差最后一步。'; $('authSubtitle').textContent = '验证邮箱，让这个空间属于你。'; $('verificationCode').focus();
    } else await finishAuth(data);
  } catch (error) {if(version === state.authVersion) notice('authError', error.message, true);}
  finally {if(version === state.authVersion) {$('authSubmit').disabled = false; $('authSubmit').textContent = mode === 'register' ? '创建账号 ↗' : '登录 ↗';}}
});
$('verificationForm').addEventListener('submit', async event => {
  event.preventDefault(); if ($('verifySubmit').disabled || !state.pendingEmail) return;
  const version = state.authVersion; $('verifySubmit').disabled = true; notice('authError', '');
  try {const data = await request('/api/auth/verify', {method:'POST', body:JSON.stringify({email:state.pendingEmail, code:$('verificationCode').value.trim()})}); if(version === state.authVersion) await finishAuth(data);}
  catch(error) {if(version === state.authVersion) notice('authError', error.message, true);}
  finally {if(version === state.authVersion) $('verifySubmit').disabled = false;}
});
$('verifyBack').onclick = () => openAuth('register');
$('passwordToggle').onclick = () => {const show = $('authPassword').type === 'password'; $('authPassword').type = show ? 'text' : 'password'; $('passwordToggle').textContent = show ? '隐藏' : '显示';};
function updateProfile() {
  const name = label();
  $('sidebarName').textContent = name; $('settingsName').textContent = name; $('settingsEmail').textContent = state.user.email;
  $('sidebarAvatar').textContent = $('settingsAvatar').textContent = Array.from(name)[0].toUpperCase();
  $('displayName').value = preferences().name || ''; $('enterToSend').checked = preferences().enterToSend !== false;
}
function addMessage(content, role) {
  $('welcome').hidden = true;
  const row = document.createElement('div'); row.className = `message ${role === 'user' ? 'user' : 'assistant'}`;
  if(role !== 'user') {const avatar = document.createElement('span'); avatar.className = 'avatar'; avatar.textContent = 'm'; row.append(avatar);}
  const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = content; row.append(bubble); $('messages').append(row);
  return row;
}
function scrollToEnd() {requestAnimationFrame(() => {$('chatScroll').scrollTop = $('chatScroll').scrollHeight;});}
let historyLoading = false;
async function loadHistory() {
  if (historyLoading) return; historyLoading = true; const version = state.sessionVersion;
  $('sendButton').disabled = true;
  try {
    const data = await request('/api/history'); if(version !== state.sessionVersion) return;
    $('messages').replaceChildren(); $('welcome').hidden = !!data.messages?.length;
    (data.messages || []).forEach(message => addMessage(message.content, message.role));
    $('historyTitle').textContent = data.messages?.find(message => message.role === 'user')?.content.slice(0,40) || '一切从一句话开始';
    state.historyReady = true; notice('chatError', ''); scrollToEnd();
  } catch(error) {if(version === state.sessionVersion) handlePrivateError(error, 'chatError');}
  finally {historyLoading = false; $('sendButton').disabled = state.busy;}
}
function handlePrivateError(error, target) {
  if(error.status === 401) {resetSession(); notice('authError', '登录已过期，请重新登录。', true);}
  else notice(target, error.message, true);
}
function resetSession() {state.sessionVersion++;state.authVersion++;state.token='';state.user=null;state.historyReady=false;localStorage.removeItem('mindtrack_token');$('messages').replaceChildren();$('welcome').hidden=false;location.hash='#/login';route();}
$('chatForm').addEventListener('submit', async event => {
  event.preventDefault(); const text = $('chatInput').value.trim(); if(!text || state.busy || historyLoading) return;
  if(!state.user) {location.hash='#/login'; return;}
  state.busy=true; const version=state.sessionVersion;
  $('sendButton').disabled=true; $('newChat').disabled=true; $('clearHistory').disabled=true;
  const row = addMessage(text,'user'); $('chatInput').value=''; $('chatInput').style.height='auto'; $('typing').hidden=false;notice('chatError','');scrollToEnd();
  try {
    const data=await request('/api/chat',{method:'POST',body:JSON.stringify({message:text})}); if(version!==state.sessionVersion)return;
    addMessage(data.reply,'assistant');$('sentimentBadge').textContent=`此刻的情绪 · ${data.sentiment || '中性'}`;
    $('historyTitle').textContent=text.slice(0,40); state.historyReady=true;scrollToEnd();
  } catch(error) {if(version===state.sessionVersion){row.remove();$('chatInput').value=text;handlePrivateError(error,'chatError');}}
  finally {state.busy=false;$('typing').hidden=true;$('sendButton').disabled=false;$('newChat').disabled=false;$('clearHistory').disabled=false;}
});
$('chatInput').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&preferences().enterToSend!==false){event.preventDefault();$('chatForm').requestSubmit();}});
$('chatInput').addEventListener('input',()=>{$('chatInput').style.height='auto';$('chatInput').style.height=`${Math.min($('chatInput').scrollHeight,180)}px`;});
document.querySelectorAll('.prompt-chip').forEach(button=>button.onclick=()=>{$('chatInput').value=button.dataset.prompt;$('chatInput').focus();});
$('profileForm').addEventListener('submit',event=>{event.preventDefault();try{savePreferences({name:$('displayName').value.trim()});updateProfile();notice('settingsStatus','称呼已保存到此浏览器。');}catch{notice('settingsStatus','浏览器无法保存设置，请检查存储权限。',true);}});
$('enterToSend').onchange=()=>{try{savePreferences({enterToSend:$('enterToSend').checked});notice('settingsStatus','发送偏好已保存到此浏览器。');}catch{notice('settingsStatus','浏览器无法保存设置。',true);}};
function confirmClear(newChat) {
  if(state.busy)return;
  $('confirmTitle').textContent=newChat?'清空记录，开始新的对话？':'清空聊天记录？';
  $('confirmDialog').returnValue='';$('confirmDialog').showModal();
  $('confirmDialog').onclose=async()=>{
    if($('confirmDialog').returnValue!=='confirm')return;
    const target=newChat?'chatError':'settingsStatus';
    try{await request('/api/history',{method:'DELETE'});$('messages').replaceChildren();$('welcome').hidden=false;$('historyTitle').textContent='一切从一句话开始';$('sentimentBadge').textContent='不必组织好语言再开始';state.historyReady=true;notice(target,'聊天记录已清空。');if(newChat){location.hash='#/chat';$('chatInput').value='';$('chatInput').focus();}}
    catch(error){handlePrivateError(error,target);}
  };
}
$('clearHistory').onclick=()=>confirmClear(false);$('newChat').onclick=()=>confirmClear(true);
$('exportHistory').onclick=async()=>{const button=$('exportHistory');button.disabled=true;try{const data=await request('/api/history');const blob=new Blob([JSON.stringify({exported_at:new Date().toISOString(),messages:data.messages},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='mindtrack-conversation.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('settingsStatus','聊天记录已导出。');}catch(error){handlePrivateError(error,'settingsStatus');}finally{button.disabled=false;}};
$('logoutBtn').onclick=async()=>{if(state.busy){notice('settingsStatus','请等待当前回复完成后退出。',true);return;}$('logoutBtn').disabled=true;try{await request('/api/auth/logout',{method:'POST'});resetSession();}catch(error){handlePrivateError(error,'settingsStatus');}finally{$('logoutBtn').disabled=false;}};
$('menuToggle').onclick=()=>{const open=!$('sidebar').classList.contains('open');$('sidebar').classList.toggle('open',open);$('sidebarBackdrop').hidden=!open;$('menuToggle').setAttribute('aria-expanded',String(open));};
$('sidebarBackdrop').onclick=closeSidebar;
window.addEventListener('keydown',event=>{if(event.key==='Escape')closeSidebar();});
window.addEventListener('hashchange',route);
async function initGoogle() {
  try {
    const config=await request('/api/config');if(!config.google_login_enabled)return;
    for(let i=0;i<20&&!window.google?.accounts?.id;i++)await new Promise(resolve=>setTimeout(resolve,300));
    if(!window.google?.accounts?.id)return;
    window.google.accounts.id.initialize({client_id:config.google_client_id,callback:async response=>{
      const version=state.authVersion;
      try{const data=await request('/api/auth/google',{method:'POST',body:JSON.stringify({credential:response.credential})});if(version===state.authVersion){state.pendingName='';await finishAuth(data);}}
      catch(error){if(version===state.authVersion)notice('authError',error.message,true);}
    }});
    window.google.accounts.id.renderButton($('googleLoginButton'),{theme:'outline',size:'large',shape:'pill',text:'continue_with'});$('googleSection').hidden=false;
  }catch{/* Email sign-in remains available when Google is unavailable. */}
}
async function init() {
  if(state.token){try{state.user=await request('/api/auth/me');}catch(error){if(error.status===401){localStorage.removeItem('mindtrack_token');state.token='';}else notice('authError',error.message,true);}}
  route();initGoogle();
}
init();
