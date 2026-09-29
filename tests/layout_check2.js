// 检查按钮/文字溢出：local、online 等待、求和提示、和棋二段式
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const MEASURE=`(()=>{
 const out={doc:document.documentElement.scrollWidth-document.documentElement.clientWidth,els:[]};
 const seen=new Set();
 const add=(e,why)=>{ if(!e||seen.has(e))return; seen.add(e);
   const r=e.getBoundingClientRect(), p=e.parentElement?e.parentElement.getBoundingClientRect():r;
   out.els.push({why,tag:e.tagName,cls:String(e.className||'').slice(0,28),txt:(e.textContent||'').trim().slice(0,18),
     sw:e.scrollWidth,cw:e.clientWidth,rw:Math.round(r.width),overR:Math.round(r.right-p.right),overL:Math.round(p.left-r.left)}); };
 document.querySelectorAll('button').forEach(b=>{ if(b.scrollWidth>b.clientWidth+1||b.getBoundingClientRect().right>(b.parentElement.getBoundingClientRect().right+1)) add(b,'button'); });
 document.querySelectorAll('.tab,.btn,.orow,.roomcode,.drawrow,.status,.hint-line,.result,.log,.pbar,.tray,.mg,.side,.layout,.wrap,.board-frame').forEach(e=>{
   if(e.scrollWidth>e.clientWidth+1) add(e,'box');
 });
 return JSON.stringify(out);})()`;
(async()=>{
  const url=process.argv[2]||'http://127.0.0.1/games/dark_chess.html';
  const cookie=process.env.PORTAL_COOKIE||null;
  let page=null;
  for(let i=0;i<40&&!page;i++){ try{ const list=await (await fetch('http://127.0.0.1:9222/json')).json();
    page=list.find(t=>t.type==='page'); }catch(e){} if(!page) await sleep(500); }
  if(!page){ console.log('NO_TARGET'); process.exit(2); }
  const ws=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r=>ws.addEventListener('open',r));
  let seq=0;
  const send=(m,p)=>new Promise(res=>{const id=++seq;const on=e=>{const x=JSON.parse(e.data);if(x.id===id){ws.removeEventListener('message',on);res(x);}};ws.addEventListener('message',on);ws.send(JSON.stringify({id,method:m,params:p}));});
  const ev=async(x)=>{const r=await send('Runtime.evaluate',{expression:x,returnByValue:true,awaitPromise:true});return r.result&&r.result.result&&r.result.result.value;};
  await send('Runtime.enable'); await send('Network.enable'); await send('Page.enable');
  if(cookie) await send('Network.setCookie',{name:'portal_cap',value:cookie,url:'http://127.0.0.1/'});
  await send('Page.navigate',{url}); await sleep(2500);
  const res=[];
  for(const w of [1440,1024,390]){
    await send('Emulation.setDeviceMetricsOverride',{width:w,height:900,deviceScaleFactor:1,mobile:w<500});
    await sleep(500);
    res.push({w,phase:'local',m:JSON.parse(await ev(MEASURE))});
    // 进入联机 + 建房（等待态）
    await ev(`(()=>{const d=document;const c=d.getElementById('tabOnline');if(c)c.dispatchEvent(new MouseEvent('click',{bubbles:true}));return 1;})()`);
    await sleep(300);
    await ev(`(()=>{const b=document.getElementById('btnCreate');if(b)b.dispatchEvent(new MouseEvent('click',{bubbles:true}));return 1;})()`);
    await sleep(1200);
    res.push({w,phase:'online-wait',m:JSON.parse(await ev(MEASURE))});
    // 求和提示 + 和棋二段式（直接把 UI 置为可见/armed 状态）
    await ev(`(()=>{const d=document;const r=d.getElementById('drawRow');if(r)r.hidden=false;const b=d.getElementById('btnDraw');if(b){b.textContent='再点一次确认和棋';b.classList.add('armed');}return 1;})()`);
    await sleep(300);
    res.push({w,phase:'draw-armed',m:JSON.parse(await ev(MEASURE))});
    await ev(`(()=>{const d=document;const r=d.getElementById('drawRow');if(r)r.hidden=true;const b=d.getElementById('btnDraw');if(b){b.textContent='和棋';b.classList.remove('armed');}const c=d.getElementById('btnCreate');if(c)c.dispatchEvent(new MouseEvent('click',{bubbles:true}));return 1;})()`);
    await sleep(600);
  }
  console.log(JSON.stringify(res,null,1)); process.exit(0);
})();
