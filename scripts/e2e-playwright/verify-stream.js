// streaming-proxy: the stream, in a real browser, through the whole chain.
//
// The bash verifier proves the relay (HTTP 200 for the client, 101 for the
// upgrade). It cannot prove that KasmVNC's own client connects and paints,
// because that needs a browser. This does.
//
//   NODE_PATH=<path>/node_modules \
//   SID=<session id> NC_BASE=http://<host>:8088 \
//   node scripts/e2e-playwright/verify-stream.js
//
// Start the session first (POST /run); the id it returns is SID. Chromium
// comes from PW_CHROME, or Playwright's own cache.
const { chromium } = require('playwright');
const EXE=process.env.PW_CHROME
  || '/home/agent/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome';
const BASE=process.env.NC_BASE||'http://192.168.178.59:8088';
const SID=process.env.SID;
let ok=0, fail=0;
const t=(n,c,x='')=>{ if(c){ok++;console.log('  ok   '+n);} else {fail++;console.log('  FAIL '+n+' '+x);} };
(async()=>{
  const b=await chromium.launch({executablePath:EXE});
  const ctx=await b.newContext();
  const p=await ctx.newPage();
  await p.goto(BASE+'/login',{waitUntil:'domcontentloaded',timeout:45000});
  await p.fill('#user','admin'); await p.fill('#password','admin-local-dev');
  await p.click('button[type=submit]'); await p.waitForTimeout(5000);

  // 1) de websocket rechtstreeks, zoals de KasmVNC-client hem opent
  const ws = await p.evaluate(async (sid) => {
    const url = location.origin.replace(/^http/,'ws')
      + `/exapps/ash_nazg/sessions/${sid}/stream/websockify`;
    return await new Promise((resolve) => {
      const gezien=[]; let s;
      const klaar=(v)=>resolve({v,gezien});
      const to=setTimeout(()=>{ try{s.close();}catch(e){} klaar('TIMEOUT'); },15000);
      try{ s=new WebSocket(url,['binary']); }catch(e){ clearTimeout(to); return klaar('FOUT'); }
      s.binaryType='arraybuffer';
      s.onopen=()=>gezien.push('open');
      s.onmessage=(e)=>{ gezien.push('bytes:'+(e.data.byteLength||String(e.data).length));
        clearTimeout(to); s.close(); klaar('GESLAAGD'); };
      s.onerror=()=>gezien.push('error');
      s.onclose=(e)=>{ clearTimeout(to); gezien.push('close:'+e.code);
        klaar(gezien.some(x=>x.startsWith('bytes:'))?'GESLAAGD':'GEFAALD'); };
    });
  }, SID);
  t('websocket door de relay draagt frames', ws.v==='GESLAAGD', JSON.stringify(ws.gezien));

  // 2) de sessiepagina met de iframe
  await p.goto(BASE+`/exapps/ash_nazg/sessions/${SID}`,
    {waitUntil:'domcontentloaded',timeout:45000});
  await p.waitForTimeout(9000);
  const frames = p.frames().map(f=>f.url());
  t('iframe wijst naar de relay', frames.some(u=>u.includes('/stream/vnc.html')), frames.join(' '));
  const kasm = p.frames().find(f=>f.url().includes('/stream/vnc.html'));
  if (kasm) {
    await p.waitForTimeout(8000);
    const staat = await kasm.evaluate(()=>{
      // De grootste canvas is het scherm; de kleintjes zijn splash en logo.
      const c = [...document.querySelectorAll('canvas')]
        .sort((a, b) => (b.width * b.height) - (a.width * a.height))[0];
      if (!c) return { canvas:false };
      // Niet alleen "er is een canvas": een splashscherm is ook een
      // canvas. Het framebuffer van de sessie is 1280x800 en bevat meer
      // dan één kleur zodra DOSBox tekent.
      const ctx = c.getContext('2d');
      const d = ctx ? ctx.getImageData(0, 0, Math.min(c.width,400), Math.min(c.height,300)).data : null;
      let kleuren = new Set();
      if (d) for (let i=0; i<d.length; i+=4*97) kleuren.add(d[i]+','+d[i+1]+','+d[i+2]);
      return { canvas:true, breed:c.width, hoog:c.height, kleuren:kleuren.size };
    }).catch(e=>({fout:String(e)}));
    t('KasmVNC tekent een canvas', staat.canvas===true, JSON.stringify(staat));
    t('canvas draagt het sessiescherm', staat.breed >= 640 && staat.hoog >= 400, JSON.stringify(staat));
    t('er staat beeld op (meer dan één kleur)', (staat.kleuren||0) > 3, JSON.stringify(staat));
  } else { fail+=3; console.log('  FAIL geen iframe gevonden'); }
  const shot = process.env.SHOT || '/tmp/ash-nazg-session.png';  // eslint-disable-line
  await p.screenshot({path:shot,fullPage:true});
  console.log('screenshot:', shot);
  await b.close();
  console.log(`\n${ok} ok, ${fail} fail`);
  process.exit(fail?1:0);
})();
