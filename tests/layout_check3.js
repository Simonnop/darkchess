// 更严格：检查按钮内部文字是否溢出按钮边界（Range 量测）+ 所有元素 scrollWidth
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const MEASURE=`(()=>{
 const out={doc:document.documentElement.scrollWidth-document.documentElement.clientWidth,bad:[]};
 document.querySelectorAll('*').forEach(e=>{ if(e.scrollWidth>e.clientWidth+1){
   const cs=getComputedStyle(e);
   out.bad.push({kind:'scroll',tag:e.tagName,cls:String(e.className||'').slice(0,26),tx:(e.textContent||'').trim().slice(0,16),sw:e.scrollWidth,cw:e.clientWidth,ox:cs.overflowX});}});
 document.querySelectorAll('button,.btn,.tab,.mini,.chip,.pbar,.tray-title').forEach(b=>{
   const r=b.getBoundingClientRect(); if(!r.width) return;
   const rg=document.createRange(); rg.selectNodeContents(b);
   const t=rg.getBoundingClientRect(); if(!t.width) return;
   if(t.right>r.right+0.5||t.left<r.left-0.5||t.bottom>r.bottom+0.5) out.bad.push({kind:'text',tag:b.tagName,cls:String(b.className||'').slice(0,26),tx:(b.textContent||'').trim().slice(0,16),tr:Math.round(t.right-r.right),tl:Math.round(r.left-t.left),tb:Math.round(t.bottom-r.bottom)});
 });
 return JSON.stringify(out);})()`;
(async()=>{
  const url=process.argv[2]||'http://127.0.0.1/games/dark_chess.html';
  let page=null;
  for(let i=0;i<40&&!page;i++){ try{ const l=await (await fetch('http://127.0.0.1:9222/json')).json(); page=l.find(t=>t.type==='page'); }catch(e){} if(!page) await sleep(500); }
  if(!page){ console.log('NO_TARGET'); process.exit(2); }
  const ws=new WebSocket(page.webSocketDebuggerUrl); await new Promise(r=>ws.addEventListener('open',r));
  let seq=0; const send=(m,p)=>new Promise(res=>{const id=++seq;const on=e=>{const x=JSON.parse(e.data);if(x.id===id){ws.removeEventListener('message',on);res(x);}};ws.addEventListener('message',on);ws.send(JSON.stringify({id,method:m,params:p}));});
  const ev=async x=>{const r=await send('Runtime.evaluate',{expression:x,returnByValue:true,awaitPromise:true});return r.result&&r.result.result&&r.result.result.value;};
  await send('Runtime.enable'); await send('Page.enable');
  await send('Page.navigate',{url}); await sleep(2500);
  for(const w of [1440,1024,768,390,360,320]){
    await send('Emulation.setDeviceMetricsOverride',{width:w,height:900,deviceScaleFactor:1,mobile:w<600}); await sleep(400);
    const states=[];
    states.push(['local',JSON.parse(await ev(MEASURE))]);
    await ev(`(()=>{const d=document;const t=d.getElementById('tabOnline');if(t)t.dispatchEvent(new MouseEvent('click',{bubbles:true}));const b=d.getElementById('btnCreate');if(b)b.dispatchEvent(new MouseEvent('click',{bubbles:true}));return 1;})()`);
    await sleep(1200);
    await ev(`(()=>{const d=document;d.getElementById('drawRow').hidden=false;const b=d.getElementById('btnDraw');b.textContent='再点一次确认和棋';b.classList.add('armed');return 1;})()`);
    await sleep(300);
    states.push(['online+draw',JSON.parse(await ev(MEASURE))]);
    await ev(`(()=>{const d=document;d.getElementById('drawRow').hidden=true;const b=d.getElementById('btnDraw');b.textContent='和棋';b.classList.remove('armed');if(d.getElementById('btnLeaveRoom'))d.getElementById('btnLeaveRoom').dispatchEvent(new MouseEvent('click',{bubbles:true}));return 1;})()`);
    await sleep(400);
    const r=states.filter(s=>s[1].doc>0||s[1].bad.length);
    console.log(`w=${w}: `+(r.length?JSON.stringify(r):'OK'));
  }
  process.exit(0);
})();
