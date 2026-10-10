/* =====================================================================
   双主播新闻节目 · 渲染核心
   载入顺序（studio.html）：core.js → package.js → scene/scene.js → film_ctrl.js → boot()
   这里放：画布、通用小工具、主播贴纸、摄像机状态、场景接口、字幕/栏目状态、
           主循环（决定各层的绘制顺序）、素材载入、场景分层导出。
   节目包装（台标、新闻栏、转场、片头、看点速报、灯光、特效）不在这里，在 package.js。
   坐标系：世界坐标 1920×1080（摄像机推拉都在这个坐标里算）。
   ===================================================================== */
const W=1920, H=1080, cv=document.getElementById('c'), ctx=cv.getContext('2d');
let T=0, last=0;
const SHOW0=(window.__FILM&&window.__FILM.show)||{}, EP0=(window.__FILM&&window.__FILM.ep)||{};

/* ---------- 小工具 ---------- */
const lerp=(a,b,t)=>a+(b-a)*t, clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const easeBack=k=>{ const c=1.9; return 1+(c+1)*Math.pow(k-1,3)+c*Math.pow(k-1,2); };
const hex=h=>[parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];
const mix=(a,b,t)=>a.map((v,i)=>Math.round(v+(b[i]-v)*t));
const rgb=(c,a=1)=>`rgba(${c[0]},${c[1]},${c[2]},${a})`;
function rnd(s){ return ()=>{ s=(s*16807)%2147483647; return s/2147483647; }; }
function mk(w,h){ const c=document.createElement('canvas'); c.width=w; c.height=h; const x=c.getContext('2d'); return [c,x]; }
const UIF='"Microsoft YaHei","PingFang SC","Noto Sans CJK SC","Noto Sans SC",sans-serif', FONT=UIF;
function rrect(g,x,y,w,h,r){ g.beginPath(); g.moveTo(x+r,y); g.arcTo(x+w,y,x+w,y+h,r); g.arcTo(x+w,y+h,x,y+h,r); g.arcTo(x,y+h,x,y,r); g.arcTo(x,y,x+w,y,r); g.closePath(); }
function vgrad(x,_,x0,y0,w,h,c0,c1,steps=8){ for(let i=0;i<h;i++){ const t=Math.floor(i/h*steps)/steps; x.fillStyle=rgb(mix(hex(c0),hex(c1),t)); x.fillRect(x0,y0+i,w,1);} }
function fitText(g,text,maxW,size,weight){ let sz=size; g.font=`${weight} ${sz}px ${UIF}`; while(g.measureText(text).width>maxW && sz>24){ sz-=2; g.font=`${weight} ${sz}px ${UIF}`; } return sz; }
const TXT={};
function pxText(str,size,color,outline,bold=true){   // 硬边像素字（做像素风场景时用）
  const key=[str,size,color,outline,bold].join('|'); if(TXT[key]) return TXT[key];
  const [c,x]=mk(1,1); x.font=`${bold?'bold ':''}${size}px ${FONT}`; const w=Math.ceil(x.measureText(str).width)+4, h=size+6;
  c.width=w; c.height=h; x.font=`${bold?'bold ':''}${size}px ${FONT}`; x.textBaseline='top'; x.fillStyle='#fff'; x.fillText(str,2,2);
  const d=x.getImageData(0,0,w,h), a=d.data, col=hex(color), m=new Uint8Array(w*h);
  for(let i=0;i<w*h;i++) m[i]=a[i*4+3]>110?1:0;
  for(let i=0;i<w*h;i++){ const o=i*4; if(m[i]){a[o]=col[0];a[o+1]=col[1];a[o+2]=col[2];a[o+3]=255;} else a[o+3]=0; }
  if(outline){ const oc=hex(outline); for(let y=0;y<h;y++)for(let xx=0;xx<w;xx++){ const i=y*w+xx; if(m[i]) continue; let n=false;
      for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){ const X=xx+dx,Y=y+dy; if(X>=0&&Y>=0&&X<w&&Y<h&&m[Y*w+X]) n=true; }
      if(n){ const o=i*4; a[o]=oc[0];a[o+1]=oc[1];a[o+2]=oc[2];a[o+3]=255; } } }
  x.putImageData(d,0,0); return TXT[key]=c;
}

/* ---------- 两位主播（整张贴纸 + 弹簧） ---------- */
function makeChar(who,x,face){ return {who,x,face,talk:false,sk:{cur:null,s:0,v:0,r:0,rv:0,next:0,prevLv:0,slow:0,refr:0}}; }
const A=makeChar('A',600,1), B=makeChar('B',1320,-1), CH={A,B};
const STK_TUNE={amp:.8,freq:3.2,damp:.35,pop:.11,size:1};
const STKIMG={A:{},B:{}}, STKSRC={A:{},B:{}};
const PREFIX={A:(SHOW0.hosts&&SHOW0.hosts.A.sticker_prefix)||'hostA',B:(SHOW0.hosts&&SHOW0.hosts.B.sticker_prefix)||'hostB'};
function prepSticker(src){   // 找到图里人物的实际范围和脚底中心，贴纸以脚底为锚点
  const w=src.width,h=src.height; let bb=null;
  try{ const [c,g]=mk(w,h); g.drawImage(src,0,0); const d=g.getImageData(0,0,w,h).data;
    let x0=w,x1=0,y0=h,y1=0; for(let y=0;y<h;y+=2) for(let x=0;x<w;x+=2) if(d[(y*w+x)*4+3]>40){ if(x<x0)x0=x; if(x>x1)x1=x; if(y<y0)y0=y; if(y>y1)y1=y; }
    if(x1>x0){ let sm=0,n=0; for(let y=Math.max(y0,y1-Math.round(h*.06)); y<=y1; y+=2) for(let x=x0;x<=x1;x+=2) if(d[(y*w+x)*4+3]>40){ sm+=x; n++; }
      bb={x0,x1,y0,y1,cx:n?sm/n:(x0+x1)/2}; } }catch(err){}
  return {img:src,w,h,bb:bb||{x0:0,x1:w,y0:0,y1:h,cx:w/2}};
}
function setSticker(c,id){ if(!STKIMG[c.who][id]) return; const k=c.sk; k.cur=id; k.s=-STK_TUNE.pop; k.v=0; k.rv+=(Math.random()<.5?-1:1)*(.15+Math.random()*.1); }
function lipSample(c){ return {level:0,bright:.5}; }
function stkUpdate(c,dt){}
function drawStickerTo(g,c){}

/* ---------- 占位贴纸：缺图时用，一眼能看出是占位 ---------- */
function labelOf(who,id){ const h=(SHOW0.hosts||{})[who]||{}, em=h.emotions||{}; for(const k in em) if(em[k]===id) return k; return id.replace(/^\d+_/,''); }
function placeholderSticker(who,id){
  const h=(SHOW0.hosts||{})[who]||{}, c1=h.c1||(who==='A'?'#ff5d73':'#2f86f0'), c2=h.c2||(who==='A'?'#ff8a5b':'#18a99c');
  const [c,g]=mk(560,1000); const cx=280;
  g.lineJoin='round'; g.lineWidth=22; g.strokeStyle='#fff';
  const body=()=>{ g.beginPath(); g.moveTo(cx-190,1000); g.bezierCurveTo(cx-200,700,cx-150,560,cx,560); g.bezierCurveTo(cx+150,560,cx+200,700,cx+190,1000); g.closePath(); };
  body(); g.stroke(); const bg=g.createLinearGradient(0,560,0,1000); bg.addColorStop(0,c1); bg.addColorStop(1,c2); g.fillStyle=bg; body(); g.fill();
  g.beginPath(); g.arc(cx,380,170,0,7); g.stroke(); g.fillStyle='#f3f4f8'; g.beginPath(); g.arc(cx,380,170,0,7); g.fill();
  g.fillStyle=c1; g.beginPath(); g.arc(cx,380,170,Math.PI*1.05,Math.PI*1.95); g.fill();
  const lab=labelOf(who,id), sad=/哭|委屈|无奈|害怕|慌/.test(lab), wow=/吃惊|惊|慌/.test(lab), mad=/生气|炸毛|不服/.test(lab);
  g.fillStyle='#2b3040'; for(const s of [-1,1]){ g.beginPath(); g.ellipse(cx+s*62,400,16,wow?26:20,0,0,7); g.fill(); }
  if(mad){ g.strokeStyle='#2b3040'; g.lineWidth=10; for(const s of [-1,1]){ g.beginPath(); g.moveTo(cx+s*95,350); g.lineTo(cx+s*35,372); g.stroke(); } }
  g.strokeStyle='#2b3040'; g.lineWidth=10; g.lineCap='round'; g.beginPath();
  if(wow){ g.arc(cx,470,22,0,7); } else if(sad){ g.arc(cx,486,34,Math.PI*1.15,Math.PI*1.85); } else { g.arc(cx,450,40,Math.PI*.2,Math.PI*.8); } g.stroke();
  g.font=`900 54px ${UIF}`; g.textAlign='center'; g.textBaseline='middle';
  const t1=(h.name||('主播'+who)), t2=lab; const tw=Math.max(g.measureText(t1).width,g.measureText(t2).width)+60;
  g.fillStyle='rgba(255,255,255,.92)'; rrect(g,cx-tw/2,680,tw,170,26); g.fill();
  g.fillStyle='#2b3040'; g.fillText(t1,cx,728); g.fillStyle=c1; g.fillText(t2,cx,800);
  g.font=`700 30px ${UIF}`; g.fillStyle='rgba(255,255,255,.85)'; g.fillText('占位 · '+PREFIX[who]+'_'+id+'.png',cx,920);
  return c;
}
/* ---------- 摄像机状态 ---------- */
const cam={x:960,y:540,z:1,r:0}, camT={x:960,y:540,z:1,r:0};
let camMode='wide', pushStart=0;
function setCam(m){}
const fx={punchA:0, punch(z){this.punchA=z||.08;}, shakeA:0, shakeX:0, shakeY:0};   // punch = 镜头轻推一下；shakeX/Y 留给包装层做震屏

/* =====================================================================
   场景接口：场景脚本调用 defineScene({...})，见 docs/scene_rules.md
   ===================================================================== */
let SCENE=null;
function defineScene(def){
  const U=SHOW0.scene||{}, o=Object.assign({},def);
  for(const k of ['screen','screen_frame','glow']) if(U[k]) o[k]=U[k];
  o.hosts=Object.assign({A:{x:600},B:{x:1320},base:905,height:640,cut_y:null},def.hosts||{});
  const uh=U.hosts||{}; for(const k of ['base','height','cut_y']) if(uh[k]!==undefined) o.hosts[k]=uh[k];
  for(const w of ['A','B']) o.hosts[w]=Object.assign({},(def.hosts||{})[w]||o.hosts[w],uh[w]||{});
  o.screen=o.screen||{x:560,y:150,w:800,h:450};
  o.screen_frame=o.screen_frame||o.screen;
  o.glow=o.glow||[o.screen.x+o.screen.w/2,o.screen.y+o.screen.h/2];
  o.palette=Object.assign({},def.palette||{},U.palette||{});
  o.cfg=U; o.back=def.back||(()=>{}); o.front=def.front||null; o.load=def.load||null;
  SCENE=o;
}
const [fgC,fgx]=mk(W,H), [ccC,ccx]=mk(W,H);
const SAPI={
  W,H, get T(){ return T; }, show:SHOW0, ep:EP0, get scene(){ return SCENE; }, get pal(){ return SCENE.palette; }, get cfg(){ return SCENE.cfg; },
  image:(p)=>new Promise(res=>{ if(!p){ res(null); return; } const im=new Image(); im.onload=()=>res(im); im.onerror=()=>{ console.warn('场景图片没找到：'+p); res(null); }; im.src='scene/'+p; }),
  cover:(g,im,x,y,w,h)=>{ if(!im) return; const k=Math.max(w/im.width,h/im.height), dw=im.width*k, dh=im.height*k; g.drawImage(im,x+(w-dw)/2,y+(h-dh)/2,dw,dh); },
  level:(who)=>{ const f=window.__FILM; return f?(f.env[who][Math.floor(T*60)]||0):0; },
  speaking:()=>(typeof CUR!=='undefined'?CUR:'A'),
  footageOn:()=>(typeof clipState!=='undefined' && clipState!=='off'),
  screenIdle:(g,r,t)=>screenIdle(g,r,t),
  pxText, vgrad, rrect, mix, hex, rgb, rnd, easeBack, lerp, clamp, mk
};
/* 大屏没放实机画面时显示的默认画面：素色底 + 节目标题图（没有就写节目名）。想做动态待机画面就在场景脚本里自己画。 */
function screenIdle(g,r,t){
  const P=SCENE.palette||{};
  g.save(); g.beginPath(); g.rect(r.x,r.y,r.w,r.h); g.clip();
  g.fillStyle=P.screen_idle||'#1d3f8f'; g.fillRect(r.x,r.y,r.w,r.h);
  const TI=window.TITLE_IMG;
  if(TI){ const tw=r.w*.72, th=tw*TI.height/TI.width, s=Math.min(1,(r.h*.7)/th); g.drawImage(TI,r.x+(r.w-tw*s)/2,r.y+(r.h-th*s)/2,tw*s,th*s); }
  else { const nm=SHOW0.show_name||''; g.textAlign='center'; g.textBaseline='middle'; let fs=Math.round(r.h*.16); g.font=`700 ${fs}px ${UIF}`;
    while(g.measureText(nm).width>r.w*.86&&fs>16){ fs-=4; g.font=`700 ${fs}px ${UIF}`; }
    g.fillStyle='#ffffff'; g.fillText(nm,r.x+r.w/2,r.y+r.h/2); }
  g.restore();
}

/* ---------- 字幕、栏目、快讯的状态（怎么画在 package.js 的 lowerThird） ---------- */
const TICKER=(EP0.ticker&&EP0.ticker.length?EP0.ticker:[]);
const SPK={A:Object.assign({name:'主播A',role:'',c1:'#ff5d73',c2:'#ff8a5b'},(SHOW0.hosts||{}).A||{}),B:Object.assign({name:'主播B',role:'',c1:'#18a99c',c2:'#2f86f0'},(SHOW0.hosts||{}).B||{})};
let SUBS=[], SECTION=EP0.section0||'', secT=0;
function setSection(t){ if(t!==SECTION){ SECTION=t; secT=T; } }
function curSub(){ for(let i=SUBS.length-1;i>=0;i--){ const s=SUBS[i]; if(!s.outAt) return s; } return null; }
function clock(){ const d=new Date(new Date((EP0.date||'2026-01-01 20:00').replace(' ','T')).getTime()+Math.floor(T)*1000); return d; }

/* ---------- 主循环（渲染时由 render.js 的虚拟时钟驱动，每帧 1/30 秒） ---------- */
function frame(now){
  const dt=Math.min(.05,(now-last)/1000); last=now; T+=dt; runEvents();
  stkUpdate(A,dt); stkUpdate(B,dt); filmCam(dt);
  const z=cam.z+fx.punchA; fx.punchA*=.88;
  ctx.setTransform(1,0,0,1,0,0); ctx.clearRect(0,0,W,H); ctx.fillStyle='#000'; ctx.fillRect(0,0,W,H);
  ctx.save(); ctx.translate(W/2+(fx.shakeX||0),H/2+(fx.shakeY||0)); ctx.rotate(cam.r); ctx.scale(z,z); ctx.translate(-cam.x,-cam.y);
  ctx.imageSmoothingEnabled=true;
  // ① 场景后景（含大屏待机画面）           —— scene.js 的 back()
  ctx.save(); SCENE.back(ctx,T,SAPI); ctx.restore();
  // ② 大屏实机画面                          —— film_ctrl.js 的 drawWallClip()
  drawWallClip();
  // ③ 主播身后的灯光（通用版留空）          —— package.js 的 behindHosts()
  ctx.save(); PKG.behindHosts(ctx,T); ctx.restore();
  // ④ 两位主播
  ccx.setTransform(1,0,0,1,0,0); ccx.clearRect(0,0,W,H); ccx.save(); if(SCENE.hosts.cut_y){ ccx.beginPath(); ccx.rect(0,0,W,SCENE.hosts.cut_y); ccx.clip(); }
  drawStickerTo(ccx,A); drawStickerTo(ccx,B); ccx.restore();
  layerBegin(); ctx.globalAlpha=charAlpha(); ctx.drawImage(ccC,0,0); ctx.globalAlpha=1; layerEnd();
  // ⑤ 场景前景（主播台等）                  —— scene.js 的 front()
  if(SCENE.front){ fgx.setTransform(1,0,0,1,0,0); fgx.clearRect(0,0,W,H); fgx.save(); SCENE.front(fgx,T,SAPI); fgx.restore();
    layerBegin(1.15); ctx.globalAlpha=charAlpha(); ctx.drawImage(fgC,0,0); ctx.globalAlpha=1; layerEnd(); }
  // ⑥ 主播前面的粒子/漫符（通用版留空）     —— package.js 的 frontOfHosts()
  layerBegin(); ctx.save(); PKG.frontOfHosts(ctx,T); ctx.restore(); layerEnd();
  ctx.restore();
  // ⑦ 屏幕层：角落主播、信息牌、要点贴纸
  drawCorner(); drawBadge(); drawKWs();
  // ⑧ 包装：台标、新闻栏、屏幕特效、板块转场、看点速报、片头 —— 全在 package.js
  for(const f of ['overlay','logo','lowerThird','effects','sectionCard','hook','sting']){ ctx.save(); ctx.setTransform(1,0,0,1,0,0); PKG[f](ctx,T); ctx.restore(); }
  // ⑨ 片尾最后 0.9 秒淡出到黑
  if(T>FILM.end-0.9){ ctx.setTransform(1,0,0,1,0,0); ctx.fillStyle=`rgba(0,0,0,${Math.min(1,(T-(FILM.end-0.9))/0.9)})`; ctx.fillRect(0,0,W,H); }
  requestAnimationFrame(frame);
}

/* ---------- 导出场景分层（pipeline scene --export）：背景、前景、参考线，拿去绘图软件里改 ---------- */
function drawGuide(g){
  const S=SCENE.screen, F=SCENE.screen_frame, Hh=SCENE.hosts, z=((SHOW0.animation||{}).camera||{}).closeup_zoom||1.38;
  g.save(); g.font=`700 24px ${UIF}`; g.textBaseline='middle'; g.lineWidth=4;
  const tag=(x,y,txt,col)=>{ const w=g.measureText(txt).width+20; x=clamp(x,4,W-w-4); y=clamp(y,4,H-38); g.fillStyle='rgba(0,0,0,.72)'; rrect(g,x,y,w,34,8); g.fill(); g.fillStyle=col; g.fillText(txt,x+10,y+17); };
  const box=(r,col,dash)=>{ g.setLineDash(dash||[]); g.strokeStyle=col; g.strokeRect(r.x,r.y,r.w,r.h); g.setLineDash([]); };
  const L=[];   // labels drawn last so they sit on top of every line
  const LH=(SHOW0.ui||{}).lower_third_height||120; g.fillStyle='rgba(255,40,60,.14)'; g.fillRect(0,H-LH,W,LH); L.push([330,H-LH+8,'新闻栏会盖住这一条（y ≥ '+(H-LH)+'）','#ff6b7a']);
  g.fillStyle='rgba(255,40,60,.14)'; g.fillRect(0,0,520,100); L.push([30,40,'台标 / LIVE','#ff6b7a']);
  for(const w of ['A','B']){ const x=Hh[w].x, f=w==='A'?A.face:B.face, vw=1920/z, vh=1080/z, CY=Hh.base-Hh.height*.63;
    const cx=clamp(x+40*f,vw/2,W-vw/2), cy=clamp(CY,vh/2,H-vh/2); box({x:cx-vw/2,y:cy-vh/2,w:vw,h:vh},'rgba(120,255,160,.85)',[2,8]);
    L.push([w==='A'?cx-vw/2+10:cx+vw/2-170,cy+vh/2-46,w+' 近景镜头','#78ffa0']); }
  if(F.x!==S.x||F.y!==S.y||F.w!==S.w||F.h!==S.h){ box(F,'#ffb020',[12,8]); L.push([F.x,F.y-40,'放画面时变暗的区域 screen_frame','#ffb020']); }
  box(S,'#ff3b4f'); L.push([S.x,S.y+S.h+8,`大屏 screen  x${S.x} y${S.y} w${S.w} h${S.h}`,'#ff6b7a']);
  for(const w of ['A','B']){ const x=Hh[w].x, hw=Hh.height*.32, col=w==='A'?'#ff7a8c':'#5cc8ff';
    box({x:x-hw,y:Hh.base-Hh.height,w:hw*2,h:Hh.height},col,[6,6]); g.strokeStyle=col; g.beginPath(); g.moveTo(x,Hh.base-Hh.height); g.lineTo(x,Hh.base); g.stroke();
    L.push([x-hw+6,Hh.base-Hh.height+8,`主播${w}  x ${x}  贴纸高 ${Hh.height}`,col]); }
  g.strokeStyle='#ffe14a'; g.setLineDash([16,10]); g.beginPath(); g.moveTo(0,Hh.base); g.lineTo(W,Hh.base); g.stroke(); g.setLineDash([]); L.push([30,Hh.base+6,'脚底线 base = '+Hh.base,'#ffe14a']);
  if(Hh.cut_y){ g.strokeStyle='#c07bff'; g.beginPath(); g.moveTo(0,Hh.cut_y); g.lineTo(W,Hh.cut_y); g.stroke(); L.push([W-360,Hh.cut_y+6,'裁切线 cut_y = '+Hh.cut_y,'#c07bff']); }
  const [gx,gy]=SCENE.glow; g.strokeStyle='#fff'; g.beginPath(); g.arc(gx,gy,14,0,7); g.moveTo(gx-24,gy); g.lineTo(gx+24,gy); g.moveTo(gx,gy-24); g.lineTo(gx,gy+24); g.stroke(); L.push([gx+22,gy+14,'灯光参考点 glow','#ffffff']);
  for(const l of L) tag(...l);
  g.restore();
}
window.exportLayers=function(){
  const out={}, [c,g]=mk(W,H), t=2;
  g.save(); SCENE.back(g,t,SAPI); g.restore(); out.back=c.toDataURL('image/png');
  g.clearRect(0,0,W,H); if(SCENE.front){ g.save(); SCENE.front(g,t,SAPI); g.restore(); } out.front=c.toDataURL('image/png');
  g.clearRect(0,0,W,H); drawGuide(g); out.guide=c.toDataURL('image/png');
  return out;
};

/* ---------- 载入：品牌图 → 包装素材 → 场景素材 → 贴纸（缺的用占位小人） ---------- */
async function boot(){
  const F=window.__FILM; if(!F){ document.body.insertAdjacentHTML('beforeend','<p style="color:#fff">这个页面要由 pipeline.py render 打开。</p>'); return; }
  if(!SCENE) defineScene({});
  const ld=src=>new Promise(res=>{ const im=new Image(); im.onload=()=>res(im); im.onerror=()=>res(null); im.src=src; });
  window.STATION_IMG=await ld('assets/station.png'); window.TITLE_IMG=await ld('assets/title.png');
  if(SCENE.load) await SCENE.load(SAPI);
  window.MISSING_STICKERS=[];
  for(const w of ['A','B']) for(const id of F.stk[w]){ const im=await ld('stk/'+PREFIX[w]+'_'+id+'.png');
    if(im){ STKIMG[w][id]=prepSticker(im); STKSRC[w][id]='file'; } else { STKIMG[w][id]=prepSticker(placeholderSticker(w,id)); STKSRC[w][id]='placeholder'; window.MISSING_STICKERS.push(PREFIX[w]+'_'+id+'.png'); } }
  if(PKG.load) await PKG.load(ld);
  for(const c of [A,B]){ const d=(SHOW0.hosts[c.who]||{}).default; c.sk.cur=STKIMG[c.who][d]?d:Object.keys(STKIMG[c.who])[0]; }
  if(window.MISSING_STICKERS.length) console.warn('缺贴纸，用占位图：'+window.MISSING_STICKERS.join('、'));
  window.FILMON=true; window.READY=true; last=performance.now(); requestAnimationFrame(frame);
}
