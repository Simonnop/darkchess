// 用 CDP 在多种宽度下检查文字溢出
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const MEASURE=`(()=>{const bad=[];const skip=e=>{const ox=getComputedStyle(e).overflowX;return ox==='auto'||ox==='scroll'||ox==='hidden';};
document.querySelectorAll('*').forEach(e=>{if(e.scrollWidth>e.clientWidth+1&&!skip(e)){
  const sb=e.className&&String(e.className).slice(0,44);bad.push({tag:e.tagName,cls:sb,sw:e.scrollWidth,cw:e.clientWidth,txt:(e.textContent||'').trim().slice(0,36)});}});
return JSON.stringify({doc:document.documentElement.scrollWidth-document.documentElement.clientWidth,window:innerWidth,bad:bad.slice(0,14)});})()`;
(async()=>{
  let page=null;
  for(let i=0;i<40&&!page;i++){
    try{ const list=await (await fetch('http://127.0.0.1:9222/json')).json();
      page=list.find(t=>t.type==='page'&&t.url.includes('dark_chess')); }catch(e){}
    if(!page) await sleep(500);
  }
  if(!page){ console.log('NO_TARGET'); process.exit(2); }
  const ws=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r=>ws.addEventListener('open',r));
  let seq=0;
  const send=(method,params)=>new Promise(res=>{const id=++seq;
    const on=e=>{const m=JSON.parse(e.data);if(m.id===id){ws.removeEventListener('message',on);res(m);}};
    ws.addEventListener('message',on); ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async(expr)=>{const r=await send('Runtime.evaluate',{expression:expr,returnByValue:true});return r.result&&r.result.result&&r.result.result.value;};
  await send('Runtime.enable');
  const out=[];
  for(const w of [1440,1024,390]){
    await send('Emulation.setDeviceMetricsOverride',{width:w,height:900,deviceScaleFactor:1,mobile:w<500});
    await sleep(400);
    out.push({w,phase:'normal',m:JSON.parse(await evaluate(MEASURE))});
    // 注入最长的真实文本：邀请链接 toast
    await evaluate(`(()=>{const s=document.getElementById('status');s.textContent='房间 ABCDEF · 你执红方（下方） · 等对方走 · 邀请链接：http://119.45.129.116/games/dark_chess.html?room=ABCDEF';const l=document.getElementById('log');if(l&&!l.innerHTML.length)l.innerHTML='<div>红方 暗子（炮位）e7→e4，翻开是 黑馬</div>';return 1;})()`);
    await sleep(250);
    out.push({w,phase:'injected',m:JSON.parse(await evaluate(MEASURE))});
  }
  console.log(JSON.stringify(out,null,1));
  process.exit(0);
})();
