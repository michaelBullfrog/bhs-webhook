const API="https://webex-contact-center-metrics.onrender.com/api/webex/contact-center";
let agents=[],timer;
const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
const state=v=>String(v||"unknown").toLowerCase().replaceAll("_","-");
const duration=s=>{s=Math.max(0,Number(s||0));const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),x=Math.floor(s%60);return [h,m,x].map(v=>String(v).padStart(2,"0")).join(":")};

function render(){
  const selected=$("stateFilter").value;
  const states=[...new Set(agents.map(a=>state(a.current_state)))].sort();
  $("stateFilter").innerHTML='<option value="">All states</option>'+states.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join("");
  if(states.includes(selected)) $("stateFilter").value=selected;

  const counts=agents.reduce((o,a)=>(o[state(a.current_state)]=(o[state(a.current_state)]||0)+1,o),{});
  $("summary").innerHTML=`<div class="summary-card"><div class="label">Total agents</div><div class="value">${agents.length}</div></div>`+
    Object.keys(counts).sort().map(s=>`<div class="summary-card"><div class="label">${esc(s)}</div><div class="value">${counts[s]}</div></div>`).join("");

  renderRows();
}
function renderRows(){
  const q=$("search").value.toLowerCase(),f=$("stateFilter").value;
  const visible=agents.filter(a=>{
    const s=state(a.current_state);
    const hay=[a.agent_name,a.agent_id,a.agent_ci_user_id,a.team_name,a.team_id,a.queue_name,a.queue_id,s,a.idle_code_name,a.wrapup_code_name,a.origin,a.destination].join(" ").toLowerCase();
    return (!f||s===f)&&(!q||hay.includes(q));
  });
  $("count").textContent=`${visible.length} agent${visible.length===1?"":"s"}`;
  $("rows").innerHTML=visible.length?visible.map(a=>{
    const s=state(a.current_state),name=a.agent_name||a.agent_email||a.agent_id;
    const reason=a.wrapup_code_name||a.idle_code_name||"—";
    const call=(a.origin||a.destination)?`${a.origin||"—"} → ${a.destination||"—"}`:"—";
    return `<tr><td><div class="agent">${esc(name)}</div><div class="sub">${esc(a.agent_id)}</div></td><td><span class="state ${esc(s)}">${esc(s)}</span></td><td>${esc(reason)}</td><td>${esc(a.team_name||a.team_id||"—")}</td><td>${esc(a.queue_name||a.queue_id||"—")}</td><td class="mono">${duration(a.state_duration_seconds)}</td><td class="mono">${esc(call)}</td></tr>`;
  }).join(""):'<tr><td colspan="7" class="empty">No matching agents.</td></tr>';
}
async function load(){
  try{
    const r=await fetch(`${API}/agents/current`,{cache:"no-store"});
    if(!r.ok) throw new Error(`API returned ${r.status}`);
    const j=await r.json();agents=Array.isArray(j.agents)?j.agents:[];
    render();$("dot").className="live";$("statusText").textContent="Live";$("updated").textContent=`Last updated ${new Date().toLocaleString()}`;
  }catch(e){console.error(e);$("dot").className="error";$("statusText").textContent="Connection error";$("updated").textContent=e.message}
}
function restart(){clearInterval(timer);timer=setInterval(load,Number($("refreshSeconds").value)*1000)}
$("search").addEventListener("input",renderRows);$("stateFilter").addEventListener("change",renderRows);$("refreshSeconds").addEventListener("change",restart);$("refreshButton").addEventListener("click",load);
load();restart();
