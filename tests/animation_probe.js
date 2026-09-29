// 在游戏页内部直接测量吃子动画时长（CDP Runtime.evaluate + awaitPromise）
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const EXPR=`(async()=>{
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 let captured=false;
 for(let attempt=0;attempt<60&&!captured;attempt++){
   const ops=[...document.querySelectorAll('.pc.op')];
   if(!ops.length) break;
   const op=ops[Math.floor(Math.random()*ops.length)];
   op.dispatchEvent(new MouseEvent('click',{bubbles:true}));
   await sleep(150);
   const caps=[...document.querySelectorAll('.mkcap,.mkring')];
   if(caps.length){ caps[Math.floor(Math.random()*caps.length)].dispatchEvent(new MouseEvent('click',{bubbles:true})); captured=true; break; }
   const mk=[...document.querySelectorAll('.mk')];
   if(mk.length){ mk[Math.floor(Math.random()*mk.length)].dispatchEvent(new MouseEvent('click',{bubbles:true})); await sleep(350); }
 }
 if(!captured) return JSON.stringify({error:'未找到吃子机会'});
 let t0=null,t1=null; const samples=[]; const start=performance.now();
 for(let i=0;i<200;i++){
   const f=document.querySelector('.flyer');
   if(f){ const now=performance.now(); if(t0===null)t0=now; t1=now;
     const inner=f.querySelector('.inner'); let sc=null;
     try{ sc=+new DOMMatrixReadOnly(getComputedStyle(inner).transform).a.toFixed(3);}catch(e){}
     const fm=new DOMMatrixReadOnly(getComputedStyle(f).transform);
     samples.push({ms:Math.round(now-start),scale:sc,flyScale:+fm.d.toFixed(2),tx:Math.round(fm.e),ty:Math.round(fm.f)});
   }
   if(t0!==null&&!f) break;
   await sleep(40);
 }
 return JSON.stringify({appeared:!!t0,durationMs:t0?Math.round(t1-t0):null,
   samples:samples.filter((s,i)=>i%4===0).slice(0,30), trayMinis:document.querySelectorAll('.mg .mini').length});
})()`;
(async()=>{
  let page=null;
  for(let i=0;i<40&&!page;i++){ try{ const l=await (await fetch('http://127.0.0.1:9222/json')).json(); page=l.find(t=>t.type==='page'); }catch(e){} if(!page) await sleep(400); }
  const ws=new WebSocket(page.webSocketDebuggerUrl); await new Promise(r=>ws.addEventListener('open',r));
  let seq=0; const send=(m,p)=>new Promise(res=>{const id=++seq;const on=e=>{const x=JSON.parse(e.data);if(x.id===id){ws.removeEventListener('message',on);res(x);}};ws.addEventListener('message',on);ws.send(JSON.stringify({id,method:m,params:p}));});
  await send('Runtime.enable');
  const r=await send('Runtime.evaluate',{expression:EXPR,returnByValue:true,awaitPromise:true});
  console.log(JSON.stringify(r.result&&r.result.result&&r.result.result.value));
  process.exit(0);
})();
