'use strict';
const $ = id => document.getElementById(id);
const state = {token: localStorage.getItem('mindtrack_token') || '', user: null, mode: 'login', pendingEmail: '', pendingName: '', authVersion: 0, sessionVersion: 0, busy: false, historyReady: false};
const companions = {
  xiaogui: {name:'小轨', icon:'🌿', tag:'温和倾听', traits:'温和 · 耐心 · 共情', motto:'慢慢说，我会认真听。', intro:'不急着给建议，也不急着下结论。先让心里的感受，被好好听见。', greeting:'今天，有什么想慢慢说的？', placeholder:'无论是什么，我都愿意听。', prompts:['我想找人听听我今天的感受。','有件事让我有点难过，想慢慢说。','我还不知道怎么表达自己的心情。']},
  nuanyang: {name:'暖阳', icon:'☀', tag:'积极鼓励', traits:'积极 · 活泼 · 行动力', motto:'一点点向前，也是一种光。', intro:'承认今天的不容易，再一起找一件做得到的小事。你不需要一下子变得很好。', greeting:'今天，我们从一件小事开始？', placeholder:'一起找一个小小的开始。', prompts:['帮我找一个今天可以完成的小目标。','最近没什么动力，想试着迈出一步。','今天做成了一件小事，想和你分享。']},
  jingyue: {name:'静月', icon:'☾', tag:'冷静理性', traits:'沉稳 · 清晰 · 善于梳理', motto:'让思绪沉淀，让方向清晰。', intro:'把纠缠的念头轻轻展开，一起分清感受、事实，以及你能改变的部分。', greeting:'我们一起，把思绪理清一点。', placeholder:'把困扰你的事情写下来。', prompts:['我脑子有点乱，帮我梳理一下。','我在两个选择之间犹豫，想理清思路。','帮我区分哪些事情是我可以控制的。']}
};
let selectedCompanion = null, companionSaving = false;
const headerCompanions = {xiaogui:'switchXiaogui', nuanyang:'switchNuanyang', jingyue:'switchJingyue'};
async function refreshConversation(data) {
  state.user.conversation_id=data.conversation_id;
  state.historyReady=false;
  $('messages').replaceChildren();$('welcome').hidden=false;$('chatInput').value='';
  $('sentimentBadge').textContent='不必组织好语言再开始';
  await loadHistory();
  await loadConversations();
}
async function loadConversations() {
  const version=state.sessionVersion;
  try {
    const data=await request('/api/conversations');if(version!==state.sessionVersion)return;
    $('conversationList').replaceChildren();
    (data.conversations||[]).forEach(item=>{
      const button=document.createElement('button');button.className='conversation-item';
      button.textContent=`${companions[item.companion]?.name || '对话'} · ${item.title}`;
      button.setAttribute('aria-current',String(item.id===state.user.conversation_id));
      button.onclick=async()=>{
        if(state.busy||companionSaving||historyLoading)return;
        companionSaving=true;updateCompanionButtons();
        try{const result=await request(`/api/conversations/${item.id}/activate`,{method:'PUT'});if(version!==state.sessionVersion)return;state.user.companion=result.companion;await refreshConversation(result);location.hash='#/chat';route();}
        catch(error){handlePrivateError(error,'chatError');}
        finally{companionSaving=false;updateCompanionButtons();}
      };
      const row=document.createElement('div');row.className='conversation-row';
      const remove=document.createElement('button');remove.className='conversation-delete';remove.textContent='×';
      remove.setAttribute('aria-label',`删除对话：${item.title}`);remove.title='删除对话';
      remove.onclick=()=>confirmDeleteConversation(item);
      row.append(button);row.append(remove);$('conversationList').append(row);
    });
  }catch(error){if(version===state.sessionVersion)notice('chatError',error.message,true);}
}
function confirmDeleteConversation(item) {
  if(state.busy||companionSaving||historyLoading)return;
  const version=state.sessionVersion;
  $('confirmTitle').textContent='删除这段对话？';
  $('confirmDescription').textContent=`将永久删除「${item.title}」及其中的消息，其他对话不会受影响。`;
  $('confirmAction').textContent='确认删除';
  $('confirmDialog').returnValue='';$('confirmDialog').showModal();
  $('confirmDialog').onclose=async()=>{
    if($('confirmDialog').returnValue!=='confirm'||version!==state.sessionVersion)return;
    companionSaving=true;updateCompanionButtons();
    try{
      await request(`/api/conversations/${item.id}`,{method:'DELETE'});
      if(version!==state.sessionVersion)return;
      if(state.user.conversation_id===item.id)await refreshConversation({conversation_id:null});
      else await loadConversations();
    }catch(error){if(version===state.sessionVersion)handlePrivateError(error,'chatError');}
    finally{companionSaving=false;updateCompanionButtons();$('sendButton').disabled=state.busy||historyLoading;}
  };
}
function updateCompanionButtons() {
  Object.entries(headerCompanions).forEach(([id, buttonId]) => {
    $(buttonId).setAttribute('aria-pressed', String(state.user?.companion === id));
    $(buttonId).disabled = state.busy || companionSaving;
  });
}
Object.entries(headerCompanions).forEach(([id, buttonId]) => {
  $(buttonId).onclick = async () => {
    if (!state.user || state.busy || historyLoading || companionSaving || state.user.companion === id) return;
    const version = state.sessionVersion;
    companionSaving = true; updateCompanionButtons(); $('sendButton').disabled = true;
    const target = location.hash === '#/settings' ? 'settingsStatus' : 'chatError';
    notice(target, '');
    try {
      const data = await request('/api/account/companion', {method:'PUT', body:JSON.stringify({companion:id})});
      if (version !== state.sessionVersion) return;
      state.user.companion = data.companion;
      await refreshConversation(data);
      applyCompanion();
      $('pageLabel').textContent = `${companions[data.companion].name} · ${companions[data.companion].tag}`;
    } catch (error) {if (version === state.sessionVersion) handlePrivateError(error, target);}
    finally {companionSaving = false; updateCompanionButtons(); $('sendButton').disabled = state.busy || historyLoading;}
  };
});
function renderCompanions() {
  selectedCompanion = state.user?.companion || null;
  $('companionChoices').replaceChildren();
  Object.entries(companions).forEach(([id, person], index) => {
    const card = document.createElement('button'); card.type='button'; card.className=`companion-card ${id}`;
    card.setAttribute('aria-pressed', String(selectedCompanion===id));
    const parts=[['card-number',`0${index+1} / ${person.tag}`],['character-orbit',person.icon],['character-name',person.name],['character-traits',person.traits],['character-motto',person.motto],['character-description',person.intro],['character-select','选择这位陪伴者 ↗']];
    parts.forEach(([className,text])=>{const part=document.createElement('span');part.className=className;part.textContent=text;card.append(part);});
    card.onclick=()=>{if(companionSaving)return;selectedCompanion=id;Array.from($('companionChoices').children).forEach(button=>button.setAttribute('aria-pressed','false'));card.setAttribute('aria-pressed','true');$('confirmCompanion').disabled=false;$('confirmCompanion').textContent=`和${person.name}开始对话 ↗`;};
    $('companionChoices').append(card);
  });
  $('confirmCompanion').disabled=!selectedCompanion;
  $('confirmCompanion').textContent=selectedCompanion?`和${companions[selectedCompanion].name}开始对话 ↗`:'选择一位陪伴者';
  $('companionBack').hidden=!state.user?.companion;
  notice('companionError','');
}
function applyCompanion() {
  updateCompanionButtons();
  const person=companions[state.user?.companion] || companions.xiaogui;
  document.body.dataset.companion=state.user?.companion || 'xiaogui';
  $('activeCompanionIcon').textContent=person.icon;
  $('companionSymbol').textContent=person.icon;
  $('companionGreeting').textContent=person.greeting;
  $('companionMotto').textContent=person.motto;
  $('companionIntro').textContent=person.intro;
  $('sidebarMotto').textContent=person.motto;
  $('settingsCompanion').textContent=`${person.name} · ${person.tag}`;
  $('settingsCompanionMotto').textContent=person.motto;
  $('chatInput').placeholder=person.placeholder;
  document.querySelectorAll('.prompt-chip').forEach((button,index)=>{button.dataset.prompt=person.prompts[index];button.querySelector('strong').textContent=person.prompts[index];button.querySelector('small').textContent=person.tag;});
  $('typing').textContent=`${person.name}正在思考…`;
}
$('confirmCompanion').onclick=async()=>{
  if(!selectedCompanion||companionSaving)return;
  const version=state.sessionVersion;companionSaving=true;$('confirmCompanion').disabled=true;
  try{const data=await request('/api/account/companion',{method:'PUT',body:JSON.stringify({companion:selectedCompanion})});if(version!==state.sessionVersion)return;state.user.companion=data.companion;await refreshConversation(data);location.hash='#/chat';route();}
  catch(error){if(version===state.sessionVersion)handlePrivateError(error,'companionError');}
  finally{companionSaving=false;$('confirmCompanion').disabled=false;}
};
$('changeCompanion').onclick=()=>{if(state.busy){notice('settingsStatus','请等待当前回复完成后更换人物。',true);return;}location.hash='#/companions';};
$('companionBack').onclick=()=>{if(!companionSaving)location.hash='#/settings';};
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
  $('companionPage').hidden=true;
  if (!state.user) {
    $('workspace').hidden = true; $('authPage').hidden = false;
    if (path !== '#/register' && path !== '#/login') {location.hash = '#/login'; return;}
    openAuth(path === '#/register' ? 'register' : 'login'); return;
  }
  if (!companions[state.user.companion] || path === '#/companions') {
    if(state.busy){location.hash='#/chat';return;}
    $('authPage').hidden=true;$('workspace').hidden=true;$('companionPage').hidden=false;
    renderCompanions();return;
  }
  applyCompanion();
  if (path !== '#/settings' && path !== '#/chat') {location.hash = '#/chat'; return;}
  $('authPage').hidden = true; $('workspace').hidden = false;
  const settings = path === '#/settings';
  $('chatPage').hidden = settings; $('settingsPage').hidden = !settings;
  $('chatNav').classList.toggle('active', !settings);
  $('accountNav').setAttribute('aria-current', settings ? 'page' : 'false');
  $('pageLabel').textContent = settings ? 'Account / Settings' : `${companions[state.user.companion].name} · ${companions[state.user.companion].tag}`;
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
  $('authSubtitle').textContent = register ? '创建账号，从一次自在的对话开始。' : '登录，继续你的 Morrow 对话。';
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
  state.user = await request('/api/auth/me');
  location.hash = companions[state.user.companion] ? '#/chat' : '#/companions'; route();
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
  if(role !== 'user') {const avatar = document.createElement('span'); avatar.className = 'avatar'; avatar.textContent = '✳'; row.append(avatar);}
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
    state.historyReady = true; notice('chatError', ''); scrollToEnd();loadConversations();
  } catch(error) {if(version === state.sessionVersion) handlePrivateError(error, 'chatError');}
  finally {historyLoading = false; $('sendButton').disabled = state.busy || companionSaving;}
}
function handlePrivateError(error, target) {
  if(error.status === 401) {resetSession(); notice('authError', '登录已过期，请重新登录。', true);}
  else notice(target, error.message, true);
}
function resetSession() {state.sessionVersion++;state.authVersion++;state.token='';state.user=null;state.historyReady=false;localStorage.removeItem('mindtrack_token');$('messages').replaceChildren();$('welcome').hidden=false;location.hash='#/login';route();}
$('chatForm').addEventListener('submit', async event => {
  event.preventDefault(); const text = $('chatInput').value.trim(); if(!text || state.busy || historyLoading || companionSaving) return;
  if(!state.user) {location.hash='#/login'; return;}
  state.busy=true; updateCompanionButtons(); const version=state.sessionVersion;
  $('sendButton').disabled=true; $('newChat').disabled=true; $('clearHistory').disabled=true;
  const row = addMessage(text,'user'); $('chatInput').value=''; $('chatInput').style.height='auto'; $('typing').hidden=false;notice('chatError','');scrollToEnd();
  try {
    const data=await request('/api/chat',{method:'POST',body:JSON.stringify({message:text})}); if(version!==state.sessionVersion)return;
    state.user.conversation_id=data.conversation_id;addMessage(data.reply,'assistant');$('sentimentBadge').textContent=`此刻的情绪 · ${data.sentiment || '中性'}`;
    $('historyTitle').textContent=text.slice(0,40); state.historyReady=true;scrollToEnd();loadConversations();
  } catch(error) {if(version===state.sessionVersion){row.remove();$('chatInput').value=text;handlePrivateError(error,'chatError');}}
  finally {state.busy=false;updateCompanionButtons();$('typing').hidden=true;$('sendButton').disabled=false;$('newChat').disabled=false;$('clearHistory').disabled=false;}
});
$('chatInput').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&preferences().enterToSend!==false){event.preventDefault();$('chatForm').requestSubmit();}});
$('chatInput').addEventListener('input',()=>{$('chatInput').style.height='auto';$('chatInput').style.height=`${Math.min($('chatInput').scrollHeight,180)}px`;});
document.querySelectorAll('.prompt-chip').forEach(button=>button.onclick=()=>{$('chatInput').value=button.dataset.prompt;$('chatInput').focus();});
$('profileForm').addEventListener('submit',event=>{event.preventDefault();try{savePreferences({name:$('displayName').value.trim()});updateProfile();notice('settingsStatus','称呼已保存到此浏览器。');}catch{notice('settingsStatus','浏览器无法保存设置，请检查存储权限。',true);}});
$('enterToSend').onchange=()=>{try{savePreferences({enterToSend:$('enterToSend').checked});notice('settingsStatus','发送偏好已保存到此浏览器。');}catch{notice('settingsStatus','浏览器无法保存设置。',true);}};
function confirmClear(newChat) {
  if(state.busy)return;
  $('confirmDescription').textContent='这会永久删除服务器上的全部聊天记录，无法恢复。';$('confirmAction').textContent='确认清空';
  $('confirmTitle').textContent=newChat?'清空记录，开始新的对话？':'清空聊天记录？';
  $('confirmDialog').returnValue='';$('confirmDialog').showModal();
  $('confirmDialog').onclose=async()=>{
    if($('confirmDialog').returnValue!=='confirm')return;
    const target=newChat?'chatError':'settingsStatus';
    try{await request('/api/history',{method:'DELETE'});$('messages').replaceChildren();$('welcome').hidden=false;$('historyTitle').textContent='一切从一句话开始';$('sentimentBadge').textContent='不必组织好语言再开始';state.historyReady=true;notice(target,'聊天记录已清空。');loadConversations();if(newChat){location.hash='#/chat';$('chatInput').value='';$('chatInput').focus();}}
    catch(error){handlePrivateError(error,target);}
  };
}
$('clearHistory').onclick=()=>confirmClear(false);$('newChat').onclick=async()=>{
  if(state.busy||companionSaving||historyLoading)return;
  companionSaving=true;updateCompanionButtons();
  try{const data=await request('/api/account/companion',{method:'PUT',body:JSON.stringify({companion:state.user.companion})});await refreshConversation(data);location.hash='#/chat';route();}
  catch(error){handlePrivateError(error,'chatError');}
  finally{companionSaving=false;updateCompanionButtons();}
};
$('exportHistory').onclick=async()=>{const button=$('exportHistory');button.disabled=true;try{const data=await request('/api/history');const blob=new Blob([JSON.stringify({exported_at:new Date().toISOString(),messages:data.messages},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='morrow-conversation.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('settingsStatus','聊天记录已导出。');}catch(error){handlePrivateError(error,'settingsStatus');}finally{button.disabled=false;}};
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
