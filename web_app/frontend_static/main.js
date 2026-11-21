// Minimal frontend logic (no frameworks)
const API_BASE = '/api';
const CHAT_STORAGE_KEY = 'finance-agent.chat.v1';
let chart = null;
let chartData = null;
let currentPath = [];
let chartItems = [];
let chatHistory = [];

function setStatus(text){document.getElementById('status').textContent = text}
function renderMessage(role, text){
  const el = document.createElement('div');
  el.className = 'chat-bubble ' + (role==='user'? 'user':'assistant');
  el.textContent = text;
  document.getElementById('chatMessages').appendChild(el);
}
function appendMessage(role, text){
  renderMessage(role, text);
  chatHistory.push({role, text});
  chatHistory = chatHistory.slice(-100);
  try{localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chatHistory));}catch(e){console.warn('Chat history could not be saved', e);}
  document.getElementById('chatMessages').scrollTop = 1e9;
}

function restoreChatHistory(){
  try{
    const stored = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '[]');
    if(!Array.isArray(stored)) return;
    chatHistory = stored.filter(item => item && ['user','assistant'].includes(item.role) && typeof item.text === 'string').slice(-100);
    chatHistory.forEach(item => renderMessage(item.role, item.text));
    document.getElementById('chatMessages').scrollTop = 1e9;
  }catch(e){
    chatHistory = [];
    console.warn('Saved chat history could not be restored', e);
  }
}

async function fetchAnalysisAll(){
  try{
    const res = await fetch(`${API_BASE}/analysis_all`);
    if(!res.ok) throw new Error('no');
    const data = await res.json();
    chartData = data;
    currentPath = [];
    renderChart(data);
    return data;
  }catch(e){console.error(e);appendMessage('assistant','Failed to load analysis.');}
}

function getNodeAtPath(node, path){
  let current = node;
  for(const name of path){
    if(!current || !current.children) return null;
    current = current.children.find((child)=>(child.name === name));
    if(!current) return null;
  }
  return current;
}

function hasChildren(node){
  return node && Array.isArray(node.children) && node.children.length > 0;
}

function buildFilters(path){
  const filters = {};
  if(path[0]) filters.account_type = path[0];
  if(path[1]) filters.bank = path[1];
  if(path[2]) filters.card_network = path[2];
  if(path[3]) filters.bucket = path[3];
  filters.start_date = null;
  filters.end_date = null;
  return filters;
}

function buildDrillButtons(children){
  const controls = document.getElementById('drillControls');
  controls.innerHTML = '';
  if(currentPath.length){
    const reset = document.createElement('button');
    reset.className = 'drill-button';
    reset.textContent = 'Top level';
    reset.onclick = async ()=>{
      currentPath = [];
      renderChart(chartData);
      document.getElementById('drillResults').innerHTML = '';
    };
    controls.appendChild(reset);
  }
  children.forEach(child=>{
    const button = document.createElement('button');
    button.className = 'drill-button';
    button.textContent = child.name;
    button.onclick = ()=>handleDrill([...currentPath, child.name]);
    controls.appendChild(button);
  });
}

async function handleDrill(path){
  currentPath = path;
  renderChart(chartData);
  setStatus('Loading drill results...');
  const filters = buildFilters(path);

  try{
    const res = await fetch(`${API_BASE}/transactions_filter`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(filters),
    });
    if(!res.ok) throw new Error('drill failed');
    const rows = await res.json();
    if (path.length === 4) {
      renderBucketDetail(path, rows);
    } else {
      renderDrillRows(path, rows);
    }
    setStatus('Idle');
  }catch(e){
    console.error(e);
    setStatus('Idle');
    appendMessage('assistant','Failed to fetch drill results');
  }
}

function renderDrillRows(path, rows){
  const container = document.getElementById('drillResults');
  container.innerHTML = '';
  const title = document.createElement('h3');
  title.textContent = 'Drill: ' + path.join(' / ');
  container.appendChild(title);
  if(!rows.length){
    const empty = document.createElement('p');
    empty.textContent = 'No transactions found for this selection.';
    container.appendChild(empty);
    return;
  }
  const summary = document.createElement('p');
  const total = rows.reduce((sum, txn) => sum + Math.abs(Number(txn.amount) || 0), 0);
  summary.textContent = `Showing ${rows.length} transactions totaling $${total.toFixed(2)}.`;
  container.appendChild(summary);
  const list = document.createElement('div');
  list.className = 'txn-list';
  rows.forEach(txn=>{
    const row = document.createElement('div');
    row.className = 'txn-row';
    row.innerHTML = `<div>${txn.date}</div><div>${txn.description}</div><div>${txn.bucket||''}</div><div>${Number(txn.amount).toFixed(2)} ${txn.currency||''}</div>`;
    list.appendChild(row);
  });
  container.appendChild(list);
}

function renderGroupResults(aq){
  const container = document.getElementById('drillResults');
  container.innerHTML = '';
  const title = document.createElement('h3');
  title.textContent = aq.title || 'Grouped results';
  container.appendChild(title);
  if(!aq.groups || !aq.groups.length){
    const empty = document.createElement('p');
    empty.textContent = 'No grouped results found for this request.';
    container.appendChild(empty);
    return;
  }
  const summary = document.createElement('p');
  summary.textContent = `Found ${aq.groups.length} groups${aq.filters && aq.filters.length ? ' for ' + aq.filters.join(', ') : ''}.`;
  container.appendChild(summary);
  const table = document.createElement('div');
  table.className = 'group-table';
  const header = document.createElement('div');
  header.className = 'group-row group-header';
  header.innerHTML = '<div>Bank</div><div>Account Type</div><div># Txns</div><div>Total</div>';
  table.appendChild(header);
  aq.groups.forEach(group => {
    const row = document.createElement('div');
    row.className = 'group-row';
    row.innerHTML = `
      <div>${group.bank || 'Unknown'}</div>
      <div>${group.account_type || 'Unknown'}</div>
      <div>${group.count || 0}</div>
      <div>$${Number(group.total || 0).toFixed(2)}</div>
    `;
    table.appendChild(row);
  });
  container.appendChild(table);
}

function renderBucketDetail(path, rows){
  const container = document.getElementById('drillResults');
  container.innerHTML = '';
  const title = document.createElement('h3');
  title.textContent = 'Bucket detail: ' + path.join(' / ');
  container.appendChild(title);
  if(!rows.length){
    const empty = document.createElement('p');
    empty.textContent = 'No transactions found in this bucket.';
    container.appendChild(empty);
    return;
  }
  const total = rows.reduce((sum, txn) => sum + Math.abs(Number(txn.amount) || 0), 0);
  const summary = document.createElement('p');
  summary.textContent = `Bucket total: $${total.toFixed(2)} across ${rows.length} transactions.`;
  container.appendChild(summary);
  const table = document.createElement('div');
  table.className = 'txn-list';
  rows.forEach(txn=>{
    const row = document.createElement('div');
    row.className = 'txn-row';
    row.innerHTML = `<div>${txn.date}</div><div>${txn.description}</div><div>${txn.category||txn.bucket||''}</div><div>${Number(txn.amount).toFixed(2)} ${txn.currency||''}</div>`;
    table.appendChild(row);
  });
  container.appendChild(table);
}

function resolveNodeValue(node){
  if (!node) return 0;
  if (typeof node.value === 'number' && node.value > 0) return Math.abs(node.value);
  if (!node.children || !node.children.length) return 0;
  return node.children.reduce((sum, child) => sum + resolveNodeValue(child), 0);
}

function normalizeChildren(node){
  return (node.children || []).map(child => ({
    name: child.name || child.label || 'Unknown',
    value: resolveNodeValue(child),
    children: child.children || [],
  }));
}

function renderChart(data){
  if(!data) return;
  const node = getNodeAtPath(data, currentPath) || data;
  const children = normalizeChildren(node);
  chartItems = children.map(child => ({name: child.name, path:[...currentPath, child.name], value:child.value}));
  const labels = chartItems.map(item => item.name);
  const values = chartItems.map(item => item.value);
  const colors = labels.map((_, idx) => ['#3B82F6','#10B981','#F59E0B','#EF4444','#8B5CF6','#22C55E'][idx % 6]);
  const ctx = document.getElementById('analysisChart').getContext('2d');
  if(chart) chart.destroy();
  chart = new Chart(ctx, {
    type:'doughnut',
    data:{labels, datasets:[{data: values, backgroundColor: colors, borderWidth: 1, borderColor: '#ffffff'}]},
    options:{
      responsive:true,
      plugins:{
        legend:{position:'bottom', labels:{color:'#334155'}},
        tooltip:{callbacks:{label: ctx => `${ctx.label}: $${ctx.raw.toLocaleString()}`}}
      },
      onClick:(evt, elems)=>{
        if(!elems.length) return;
        const item = chartItems[elems[0].index];
        if(item) handleDrill(item.path);
      }
    }
  });
  buildDrillButtons(children);
}

async function sendChat(){
  const input = document.getElementById('chatInput');
  const fileInput = document.getElementById('fileInput');
  const text = input.value.trim();
  const file = fileInput.files[0];
  if(!text && !file) return;
  if(file){
    appendMessage('user', `Uploading ${file.name}...`);
    setStatus('Uploading file...');
    const fd = new FormData();
    fd.append('file', file);
    try{
      const up = await fetch(`${API_BASE}/upload`, {method:'POST', body:fd});
      const info = await up.json();
      appendMessage('assistant', info.message || 'Uploaded');
      setStatus('Processing file...');
      const proc = await (await fetch(`${API_BASE}/chat`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:'process it now', fileId: info.fileId})})).json();
      appendMessage('assistant', proc.reply || proc.message || 'Processed');
      await fetchAnalysisAll();
      setStatus('Idle');
    }catch(e){
      console.error(e);
      appendMessage('assistant','Upload failed');
      setStatus('Idle');
    }
    fileInput.value = '';
    input.value = '';
    return;
  }

  appendMessage('user', text);
  input.value = '';
  setStatus('Processing...');
  try{
    const history = chatHistory.slice(0, -1).slice(-12);
    const response = await fetch(`${API_BASE}/chat`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:text, history})});
    const resp = await response.json();
    if(!response.ok) throw new Error(resp.reply || 'Chat query failed');
    appendMessage('assistant', resp.reply || resp.message || 'Reply');
    setStatus('Idle');
  }catch(e){
    console.error(e);
    appendMessage('assistant', e.message || 'Chat failed');
    setStatus('Idle');
  }
}

window.addEventListener('load', async ()=>{
  restoreChatHistory();
  document.getElementById('sendBtn').addEventListener('click', sendChat);
  document.getElementById('chatInput').addEventListener('keydown', (e)=>{ if(e.key==='Enter') sendChat(); });
  setStatus('Loading analysis...');
  await fetchAnalysisAll();
  setStatus('Idle');
});
