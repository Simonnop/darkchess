// 通过 CDP 轮询页面里的 __DSTEST 结果
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  let page=null;
  for(let i=0;i<40 && !page;i++){
    try{
      const list=await (await fetch('http://127.0.0.1:9222/json')).json();
      page=list.find(t=>t.type==='page'&&t.url.includes('_dstest'));
    }catch(e){}
    if(!page) await sleep(500);
  }
  if(!page){ console.log('NO_TARGET'); process.exit(2); }
  const ws=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r=>ws.addEventListener('open',r));
  let seq=0;
  const send=(method,params)=>new Promise(res=>{
    const id=++seq;
    const on=e=>{ const m=JSON.parse(e.data); if(m.id===id){ ws.removeEventListener('message',on); res(m); } };
    ws.addEventListener('message',on);
    ws.send(JSON.stringify({id,method,params}));
  });
  for(let i=0;i<180;i++){
    const r=await send('Runtime.evaluate',{expression:'JSON.stringify(window.__DSTEST||null)',returnByValue:true});
    const v=r.result&&r.result.result&&r.result.result.value;
    if(v&&v!=='null'){ console.log(v); process.exit(0); }
    await sleep(1000);
  }
  console.log('TIMEOUT');
  process.exit(3);
})();
