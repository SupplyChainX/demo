// Assistant V2 – Clean rebuilt UI layer
// Keeps existing backend endpoints; removes dynamic DOM reconstruction + legacy complexity

class SupplyChainAssistantV2 {
  constructor(opts={}) {
    this.cfg = Object.assign({
      endpoints: {
        startSession: '/api/assistant/start-session',
        chat: '/api/assistant/chat'
      }
    }, opts);
  this.state = {sessionId:null, processing:false, lastUserMessage:null, replay:false, atBottom:true, newSinceScroll:0};
    this.storage = {
      sessionKey: 'scx_assistant_session_v2',
      historyKey: 'scx_assistant_history_v2'
    };
    this.root = document.getElementById('ai-assistant-v2');
    this.trigger = document.getElementById('assistantTriggerV2');
    if (!this.root) return; // fail silently
    this.cacheDom();
    this.bindEvents();
    this.init();
  }

  cacheDom(){
    this.headerCtx = this.root.querySelector('.context-label');
    this.messages = this.root.querySelector('.messages');
    this.textarea = this.root.querySelector('textarea');
    this.sendBtn = this.root.querySelector('button.send');
    this.typing = this.root.querySelector('.typing');
    // Scroll anchor button (create once)
    if(this.messages && !this.root.querySelector('.scroll-anchor')){
      const btn = document.createElement('button');
      btn.type='button';
      btn.className='scroll-anchor';
      btn.hidden = true;
      btn.textContent = 'Jump to latest';
      btn.addEventListener('click', ()=> this.scrollToLatest(true));
      this.root.appendChild(btn);
    }
    this.anchorBtn = this.root.querySelector('.scroll-anchor');
  }

  bindEvents(){
    this.sendBtn.addEventListener('click', ()=> this.sendMessage());
    this.textarea.addEventListener('keydown', e=>{if(e.key==='Enter' && !e.shiftKey){e.preventDefault();this.sendMessage();}});
    this.textarea.addEventListener('input', ()=> this.autosize());
    this.root.querySelector('.btn-min').addEventListener('click', ()=> this.toggle());
    if (this.trigger){this.trigger.querySelector('button').addEventListener('click',()=>this.toggle(true));}
    document.addEventListener('keydown', e=>{if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();this.focus();}});
    if(this.messages){
      this.messages.addEventListener('scroll', ()=>{
        const nearBottom = (this.messages.scrollHeight - (this.messages.scrollTop + this.messages.clientHeight)) < 80;
        this.state.atBottom = nearBottom;
        if(nearBottom){
          this.state.newSinceScroll = 0;
          if(this.anchorBtn) this.anchorBtn.hidden = true;
        }
      }, {passive:true});
    }
  }

  async init(){
    this.updateStatus('connecting');
    // Attempt to restore session + history
    this.restoreSession();
    this.restoreHistory();
    try {
      if(!this.state.sessionId){
        await this.startSession();
        this.welcome();
      } else if(this.messages.childElementCount===0) {
        // If session restored but UI empty, show welcome once
        this.welcome();
      }
      this.updateStatus('connected');
    } catch(err){
      console.error('Init error – starting fresh session', err);
      // Fallback: try fresh session
      try { await this.startSession(true); this.welcome(); this.updateStatus('connected'); }
      catch(e2){ console.error(e2); this.systemMsg('Failed to initialize assistant.'); this.updateStatus('error'); }
    }
  }

  updateStatus(status){
    this.root.classList.remove('connected','error');
    if (status==='connected') this.root.classList.add('connected');
    if (status==='error') this.root.classList.add('error');
  }

  async startSession(){
    const context = this.buildContext();
    const r = await fetch(this.cfg.endpoints.startSession,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page_info:context.page_info,current_data:context.current_data})});
    const d = await r.json();
    if(!d.success) throw new Error(d.error||'session');
  this.state.sessionId = d.session_id;
  this.persistSession();
  }

  buildContext(){
    return {page_info:{path:location.pathname,title:document.title,type:'general',timestamp:new Date().toISOString()},current_data:{}}; // minimal for v2
  }

  welcome(){
    this.aiMsg("Hello! I'm your SupplyChainX AI Assistant. Ask about shipments, suppliers, risks, routes or analytics.");
  }

  focus(){this.textarea.focus();}

  autosize(){
    const ta = this.textarea; ta.style.height='auto'; ta.style.height = Math.min(ta.scrollHeight,140)+'px';
  }

  toggle(fromTrigger=false){
    this.root.classList.toggle('minimized');
    const minimized = this.root.classList.contains('minimized');
    if(this.trigger) this.trigger.style.display = minimized ? 'block':'none';
    if(!minimized) this.focus();
  }

  sendMessage(){
    const val = this.textarea.value.trim();
  if(!val || this.state.processing) return; this.textarea.value=''; this.autosize(); this.state.lastUserMessage = val; this.userMsg(val); this.request(val);
  }

  async request(message){
    this.state.processing = true; this.setSending(true); this.showTyping(true);
    try {
      const r = await fetch(this.cfg.endpoints.chat,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,session_id:this.state.sessionId,page_context:this.buildContext()})});
      const d = await r.json();
      this.showTyping(false);
      if(d.success){
        const aiText = d.response || d.message || '(No content)';
        this.aiMsg(aiText);
        // Display action buttons if available
        if(d.actions && d.actions.length > 0) {
          this.addActionButtons(d.actions);
        }
      } else {
        this.systemMsg(d.error||'Request failed', {retry:true});
        if(d.fallback_response) this.aiMsg(d.fallback_response);
        // Handle possible invalid session -> restart once
        if(/session/i.test(d.error||'') && !this._restarted){
          this._restarted = true;
          await this.startSession();
        }
      } 
    } catch(err){ console.error(err); this.showTyping(false); this.systemMsg('Network error. Please retry.', {retry:true}); }
    this.state.processing = false; this.setSending(false); this.focus();
  }

  setSending(on){ this.sendBtn.disabled = on; this.sendBtn.innerHTML = on?'<i class="fas fa-spinner fa-spin"></i>':'<i class="fas fa-paper-plane"></i>'; }
  showTyping(show){ if(!this.typing) return; if(show){this.typing.hidden=false;} else {this.typing.hidden=true;} this.scrollBottom(); }
  scrollBottom(){ this.messages.scrollTop = this.messages.scrollHeight; }

  userMsg(txt){ this.addMsg('user',txt); }
  aiMsg(txt){ this.addMsg('ai',txt); }
  systemMsg(txt, opts={}){ this.addMsg('sys',txt, opts); }

  addMsg(kind,txt, opts={}){
    const wrap = document.createElement('div');
    wrap.className = (kind==='ai'?'ai-msg':kind==='user'?'user-msg':'sys-msg');
    const icon = kind==='user'?'user':(kind==='ai'?'robot':'exclamation-triangle');
    const rendered = (kind==='ai') ? this.renderMarkdown(txt) : this.escape(txt);
    const retryButton = (kind==='sys' && opts.retry && this.state.lastUserMessage) ? `<button class="retry-btn" type="button" data-retry="1" title="Retry last message"><i class="fas fa-redo"></i> Retry</button>` : '';
    wrap.innerHTML = `<div class="msg-avatar"><i class="fas fa-${icon}"></i></div><div class="msg-bubble"><div class="msg-text">${rendered}</div>${retryButton?`<div class="retry-container">${retryButton}</div>`:''}<div class="msg-meta"><span>${this.now()}</span></div></div>`;
    this.messages.appendChild(wrap); this.scrollBottom();
    // Anchor logic: if user scrolled up and a new AI message arrives, show anchor
    if(kind==='ai'){
      const nearBottom = (this.messages.scrollHeight - (this.messages.scrollTop + this.messages.clientHeight)) < 80;
      if(nearBottom){
        this.scrollToLatest();
      } else {
        this.state.atBottom = false;
        this.state.newSinceScroll++;
        this.updateAnchorButton();
      }
    }
    // Attach retry handler if present
    if(retryButton){
      const btn = wrap.querySelector('.retry-btn');
      if(btn){
        btn.addEventListener('click', ()=>{
          if(!this.state.lastUserMessage || this.state.processing) return;
          this.request(this.state.lastUserMessage);
          btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        });
      }
    }
  // Persist unless disabled (replay) or explicitly turned off
  const persist = opts.persist !== false && !this.state.replay;
  if(persist && (kind==='user' || kind==='ai')) this.persistMessage({role:kind==='user'?'user':'assistant', content:txt, ts:Date.now()});
  }

  scrollToLatest(force=false){
    if(!this.messages) return;
    if(force){
      this.messages.scrollTop = this.messages.scrollHeight;
      this.state.atBottom = true;
      this.state.newSinceScroll = 0;
      this.updateAnchorButton();
      return;
    }
    if(this.state.atBottom){
      this.messages.scrollTop = this.messages.scrollHeight;
    }
  }

  updateAnchorButton(){
    if(!this.anchorBtn) return;
    if(this.state.newSinceScroll>0){
      this.anchorBtn.hidden = false;
      this.anchorBtn.textContent = this.state.newSinceScroll===1 ? '1 new message' : `${this.state.newSinceScroll} new messages`;
    } else {
      this.anchorBtn.hidden = true;
    }
  }

  escape(t){const d=document.createElement('div');d.textContent=t;return d.innerHTML;}
  now(){return new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});}  

  // Basic safe markdown: **bold**, inline `code`, unordered (- or *), ordered (1.) lists, line breaks
  renderMarkdown(text){
    if(!text) return '';
    // Escape first
    let safe = this.escape(text);
    const codeStore = [];
    const blockStore = [];
    // Fenced code blocks ```lang\n...```
    safe = safe.replace(/```(\w+)?\n([\s\S]*?)```/g,(m,lang,code)=>{
      const idx = blockStore.length;
      blockStore.push(`<pre class=\"code-block\"><code${lang?` data-lang=\"${lang}\"`:''}>${this.escape(code)}</code></pre>`);
      return `%%BLOCK${idx}%%`;
    });
    // Inline code
    safe = safe.replace(/`([^`]+)`/g,(m,p1)=>{codeStore.push(`<code>${p1}</code>`); return `%%CODE${codeStore.length-1}%%`;});
    // Bold
    safe = safe.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
    // Italic (single * or _ not part of bold)
    safe = safe.replace(/(^|[^*_])\*(?!\*)([^*]+?)\*(?!\*)/g,'$1<em>$2</em>');
    safe = safe.replace(/(^|[^*_])_(?!_)([^_]+?)_(?!_)/g,'$1<em>$2</em>');

    const lines = safe.split(/\r?\n/);
    const out = [];
    let listMode = null; // 'ul' | 'ol'
    let listBuffer = [];
    let listStart = 1;
    const flushList = ()=>{ if(listMode && listBuffer.length){ const startAttr = (listMode==='ol' && listStart!==1)?` start=\"${listStart}\"`:''; out.push(`<${listMode}${startAttr}>`+listBuffer.join('')+`</${listMode}>`); listMode=null; listBuffer=[]; listStart=1; } };

    // Table detection helpers
    const isTableSeparator = l=>/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(l);
    const isTableRow = l=>/^\s*\|.*\|\s*$/.test(l);

    for(let i=0;i<lines.length;i++){
      let line = lines[i];
      // Table parsing: header |---| line then rows
      if(isTableRow(line) && i+1<lines.length && isTableSeparator(lines[i+1])){
        flushList();
        const header = line;
        i++; // skip separator
        const rows = [];
        while(i+1<=lines.length){
          const peek = lines[i+1];
            if(peek && isTableRow(peek)) { rows.push(peek); i++; } else break;
        }
        const headCells = header.replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
        const bodyRows = rows.map(r=>r.replace(/^\||\|$/g,'').split('|').map(c=>c.trim()));
        let tbl = '<table class="md-table"><thead><tr>' + headCells.map(c=>`<th>${c}</th>`).join('') + '</tr></thead><tbody>' + bodyRows.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join('') + '</tbody></table>';
        out.push(tbl);
        continue;
      }

      const ulMatch = /^\s*[-*]\s+(.+)$/.exec(line);
      const olMatch = /^\s*(\d+)\.\s+(.+)$/.exec(line);
      if(ulMatch){
        if(listMode && listMode!=='ul') flushList();
        listMode='ul'; listBuffer.push(`<li>${ulMatch[1]}</li>`);
      } else if(olMatch){
        if(listMode && listMode!=='ol') flushList();
        if(listMode!=='ol') listStart = parseInt(olMatch[1],10)||1; // capture starting index
        listMode='ol'; listBuffer.push(`<li>${olMatch[2]}</li>`);
      } else {
        flushList();
        if(line.trim()===''){ out.push('<br>'); }
        else out.push(`<p>${line}</p>`);
      }
    }
    flushList();
    let html = out.join('');
    // Restore inline code
    html = html.replace(/%%CODE(\d+)%%/g,(m,i)=>codeStore[i]||'');
    // Restore blocks
    html = html.replace(/%%BLOCK(\d+)%%/g,(m,i)=>blockStore[i]||'');
    return html;
  }


  // Persistence helpers
  persistSession(){ try{ localStorage.setItem(this.storage.sessionKey, this.state.sessionId); }catch(e){} }
  restoreSession(){ try{ const sid = localStorage.getItem(this.storage.sessionKey); if(sid) this.state.sessionId = sid; }catch(e){} }
  persistMessage(msg){
    try {
      const arr = JSON.parse(localStorage.getItem(this.storage.historyKey) || '[]');
      arr.push(msg);
      // Cap history length to prevent bloat
      while(arr.length>200) arr.shift();
      localStorage.setItem(this.storage.historyKey, JSON.stringify(arr));
    } catch(e) { console.warn('Persist message failed', e); }
  }
  restoreHistory(){
    try {
      let arr = JSON.parse(localStorage.getItem(this.storage.historyKey) || '[]');
      if(!Array.isArray(arr) || arr.length===0) return;
      // Deduplicate (keep first occurrence of role+content)
      const seen = new Set();
      const dedup = [];
      for(const m of arr){
        const key = m.role+'|'+m.content.trim();
        if(!seen.has(key)) { seen.add(key); dedup.push(m); }
      }
      if(dedup.length !== arr.length){
        localStorage.setItem(this.storage.historyKey, JSON.stringify(dedup));
        arr = dedup;
      }
      this.state.replay = true;
      arr.forEach(m=>{
        if(m.role==='user') this.addMsg('user', m.content, {persist:false});
        else if(m.role==='assistant') this.addMsg('ai', m.content, {persist:false});
      });
      this.state.replay = false;
    } catch(e) { console.warn('Restore history failed', e); this.state.replay=false; }
  }

  addActionButtons(actions) {
    if (!actions || actions.length === 0) return;
    
    const actionsContainer = document.createElement('div');
    actionsContainer.className = 'action-buttons-container';
    actionsContainer.innerHTML = `
      <div class="actions-header">
        <i class="fas fa-bolt"></i>
        <span>Suggested Actions</span>
      </div>
      <div class="actions-grid"></div>
    `;
    
    const grid = actionsContainer.querySelector('.actions-grid');
    
    actions.forEach(action => {
      const button = document.createElement('button');
      button.className = `action-button action-${action.type}`;
      button.innerHTML = `
        <i class="fas fa-${this.getActionIcon(action.type)}"></i>
        <span class="action-label">${action.label}</span>
        ${action.description ? `<span class="action-description">${action.description}</span>` : ''}
      `;
      
      button.addEventListener('click', () => this.executeAction(action));
      grid.appendChild(button);
    });
    
    this.messages.appendChild(actionsContainer);
    this.scrollBottom();
  }

  getActionIcon(type) {
    switch(type) {
      case 'navigate': return 'external-link-alt';
      case 'search_shipment': return 'search';
      case 'generate_report': return 'file-alt';
      case 'show_urgent_items': return 'exclamation-triangle';
      case 'show_recent_activity': return 'clock';
      case 'show_recommendations': return 'lightbulb';
      default: return 'arrow-right';
    }
  }

  executeAction(action) {
    console.log('Executing action:', action);
    
    switch (action.type) {
      case 'navigate':
        window.location.href = action.data;
        break;
        
      case 'search_shipment':
        this.searchShipment(action.data);
        break;
        
      case 'generate_report':
        this.generateReport(action.data);
        break;
        
      case 'show_urgent_items':
        this.showUrgentItems(action.data);
        break;
        
      case 'show_recent_activity':
        this.showRecentActivity(action.data);
        break;
        
      case 'show_recommendations':
        this.showRecommendations(action.data);
        break;
        
      default:
        console.warn('Unknown action type:', action.type);
        this.systemMsg(`Action "${action.type}" is not yet supported.`);
    }
  }

  // Placeholder methods for different action types
  searchShipment(data) {
    this.systemMsg('Searching for shipment... (Feature coming soon)');
  }

  generateReport(data) {
    this.systemMsg('Generating report... (Feature coming soon)');
  }

  showUrgentItems(data) {
    this.systemMsg('Loading urgent items... (Feature coming soon)');
  }

  showRecentActivity(data) {
    this.systemMsg('Loading recent activity... (Feature coming soon)');
  }

  showRecommendations(data) {
    this.systemMsg('Loading recommendations... (Feature coming soon)');
  }
}

window.addEventListener('DOMContentLoaded',()=>{window.scxAssistantV2 = new SupplyChainAssistantV2();});
