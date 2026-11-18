const $ = id => document.getElementById(id);
let equityChart, allocationChart, candleData = [];

async function api(path){ const r=await fetch(path); if(!r.ok) throw new Error(`API ${r.status}`); return r.json(); }
const money = n => '$'+Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
function setText(id,value){$(id).textContent=value;}

async function loadOverview(){
  const d=await api('/api/overview');
  setText('balance',money(d.balance)); setText('equity',money(d.equity));
  setText('pnl',(d.daily_pnl>=0?'+':'')+money(d.daily_pnl));
  $('pnl').className='text-2xl font-bold mt-3 '+(d.daily_pnl>=0?'positive':'negative');
  setText('pnlPct',`${d.daily_pnl_pct>=0?'+':''}${d.daily_pnl_pct}% today`);
  setText('winRate',d.win_rate+'%'); setText('updatedAt','Updated '+new Date(d.updated_at).toLocaleTimeString());
}
async function loadMarkets(){
  const rows=await api('/api/markets');
  $('marketRows').innerHTML=rows.map(x=>`<tr class="border-b border-slate-800/80"><td class="py-4"><div class="font-semibold">${x.symbol}</div><div class="text-xs muted">${x.name}</div></td><td class="text-right font-medium">${x.price.toLocaleString()}</td><td class="text-right ${x.change>=0?'positive':'negative'}">${x.change>0?'+':''}${x.change}%</td><td class="text-right muted">${x.spread}</td><td class="text-right text-xs muted">${x.status}</td></tr>`).join('');
}
async function loadPositions(){
  const rows=await api('/api/positions'); setText('positionCount',rows.length+' OPEN');
  $('positionRows').innerHTML=rows.map(x=>`<tr class="border-b border-slate-800/80"><td class="py-4 font-semibold">${x.symbol}</td><td class="${x.side==='BUY'?'positive':'negative'}">${x.side}</td><td>${x.entry}</td><td>${x.current}</td><td class="muted">${x.sl}</td><td class="muted">${x.tp}</td><td class="text-right font-semibold ${x.pnl>=0?'positive':'negative'}">${x.pnl>=0?'+':''}${money(x.pnl)}</td></tr>`).join('');
}
async function loadSignals(){
  const rows=await api('/api/signals');
  $('signalRows').innerHTML=rows.map(x=>`<tr class="border-b border-slate-800/80"><td class="py-4 muted">${x.time}</td><td class="font-semibold">${x.symbol}</td><td class="${x.side==='BUY'?'positive':'negative'}">${x.side}</td><td>${x.strategy}</td><td class="muted">${x.tf}</td><td><span class="text-sky-300">${x.confidence}/100</span></td><td><span class="tag bg-amber-400/10 text-amber-300">${x.status}</span></td></tr>`).join('');
}
async function loadEquity(){
  const d=await api('/api/equity');
  if(equityChart) equityChart.destroy();
  equityChart=new Chart($('equityChart'),{type:'line',data:{labels:d.labels,datasets:[{label:'Demo equity',data:d.values,borderColor:'#2dd4a7',backgroundColor:'rgba(45,212,167,.10)',fill:true,tension:.35,pointRadius:0,borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#8293aa',maxTicksLimit:7},grid:{display:false}},y:{ticks:{color:'#8293aa',callback:v=>'$'+v.toLocaleString()},grid:{color:'rgba(148,163,184,.10)'}}}}});
  if(allocationChart) allocationChart.destroy();
  allocationChart=new Chart($('allocationChart'),{type:'doughnut',data:{labels:['Forex & Gold','Crypto'],datasets:[{data:[58,42],backgroundColor:['#2dd4a7','#60a5fa'],borderWidth:0,hoverOffset:5}]},options:{responsive:true,maintainAspectRatio:false,cutout:'72%',plugins:{legend:{display:false}}}});
}
async function loadCandles(){
  const symbol=$('symbolSelect').value, tf=$('tfSelect').value;
  const d=await api(`/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}`);
  candleData=d.candles; drawCandles();
}
function drawCandles(){
  const canvas=$('candleCanvas'), rect=canvas.getBoundingClientRect(), dpr=window.devicePixelRatio||1;
  canvas.width=Math.max(1,rect.width*dpr); canvas.height=Math.max(1,rect.height*dpr);
  const ctx=canvas.getContext('2d'); ctx.scale(dpr,dpr);
  const w=rect.width,h=rect.height,pad={l:12,r:65,t:12,b:22}, cw=w-pad.l-pad.r,ch=h-pad.t-pad.b;
  ctx.clearRect(0,0,w,h);
  if(!candleData.length)return;
  const min=Math.min(...candleData.map(c=>c.low)), max=Math.max(...candleData.map(c=>c.high)), range=max-min||1;
  const y=v=>pad.t+(max-v)/range*ch;
  ctx.font='10px system-ui'; ctx.fillStyle='#8293aa'; ctx.strokeStyle='rgba(148,163,184,.13)';
  for(let i=0;i<=4;i++){let yy=pad.t+ch*i/4;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();let val=max-range*i/4;ctx.fillText(val.toFixed(2),w-pad.r+8,yy+3);}
  const step=cw/candleData.length, body=Math.max(3,step*.58);
  candleData.forEach((c,i)=>{
    const x=pad.l+i*step+step/2, up=c.close>=c.open, color=up?'#2dd4a7':'#fb7185';
    ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,y(c.high));ctx.lineTo(x,y(c.low));ctx.stroke();
    const top=Math.min(y(c.open),y(c.close)), height=Math.max(1,Math.abs(y(c.open)-y(c.close)));
    ctx.fillRect(x-body/2,top,body,height);
  });
  // Illustrative 20-period moving average overlay
  ctx.beginPath();ctx.strokeStyle='#2dd4a7';ctx.lineWidth=1.5;
  candleData.forEach((c,i)=>{const slice=candleData.slice(Math.max(0,i-19),i+1);const avg=slice.reduce((s,v)=>s+v.close,0)/slice.length;const x=pad.l+i*step+step/2;i?ctx.lineTo(x,y(avg)):ctx.moveTo(x,y(avg));});ctx.stroke();
}
async function refresh(){
  try{await Promise.all([loadOverview(),loadMarkets(),loadPositions(),loadSignals(),loadEquity(),loadCandles()]);}
  catch(e){console.error(e);alert('Could not load dashboard demo API. Is the Python server running?');}
}
$('refreshBtn').addEventListener('click',refresh);
$('symbolSelect').addEventListener('change',loadCandles);
$('tfSelect').addEventListener('change',loadCandles);
window.addEventListener('resize',()=>{if(candleData.length)drawCandles();});
refresh();
