/* =====================================================================
   节目控制器：按 film.json 的时间线驱动主播贴纸、镜头、大屏实机画面、
   要点贴纸、信息牌，并把包装需要的状态交给 package.js。
   读取场景几何（SCENE）：大屏位置、主播站位。
   这里只管「什么时候发生什么」，不管包装长什么样。
   ===================================================================== */
var FILM = window.__FILM; var SHOW=FILM.show, EP=FILM.ep;
var deep=(d,u)=>{ const o=JSON.parse(JSON.stringify(d)); for(const k in (u||{})) if(o[k]) Object.assign(o[k],u[k]); return o; };
/* ---------- 动画参数（show.json → animation 可覆盖，见 docs/animation_rules.md） ---------- */
var AN=deep({
  talk:{amp:1.15,freq:3.4,damp:.26,onset:.18,rise:.04,gap:.11,kick:.6,kick_lv:.8,tilt:.22,breath:.008},
  switch:{pop:.17,jump_big:520,jump_small:300,jump_hz:2.6,jump_damp:.32,land_jump:620,land_squash:.16},
  camera:{spring_hz:1.5,spring_damp:.58,closeup_zoom:1.38,dutch_zoom:1.3,dutch_angle:-.05,push_rate:.06,push_max:.4,
          wall_in:.6,wall_overshoot:1.05,wall_flash:.55,wall_out:.62,return_delay:1.5}
}, SHOW.animation);
var UIC=Object.assign({keyword_hold:2.9,keyword_max:3},SHOW.ui||{});
Object.assign(STK_TUNE,{amp:AN.talk.amp,freq:AN.talk.freq,damp:AN.talk.damp,pop:AN.switch.pop});
var STUDIO={base:SCENE.hosts.base,h:SCENE.hosts.height};
A.x=SCENE.hosts.A.x; B.x=SCENE.hosts.B.x;
var CLOSE_Y=STUDIO.base-STUDIO.h*.63;            // 近景镜头对准主播上半身
lipSample=c=>({level:(FILM.env[c.who][Math.floor(T*60)]||0),bright:.5});
var CUR='A';
var ease=k=>k<.5?4*k*k*k:1-Math.pow(-2*k+2,3)/2;
var elastic=a=>Math.exp(-a*6)*Math.sin(a*22);
var easeIn3=k=>k*k*k, easeOut3=k=>1-Math.pow(1-k,3);

/* ---------- 镜头：弹簧跟随 + 推进大屏的补间 ---------- */
var camV={x:0,y:0,z:0,r:0}, camTw=null;
setCam=function(m){ camMode=m; pushStart=T;
  if(m==='wide') Object.assign(camT,{x:960,y:540,z:1,r:0});
  if(m==='A') Object.assign(camT,{x:A.x+40*A.face,y:CLOSE_Y,z:AN.camera.closeup_zoom,r:0});
  if(m==='B') Object.assign(camT,{x:B.x+40*B.face,y:CLOSE_Y,z:AN.camera.closeup_zoom,r:0});
  if(m==='dutch') Object.assign(camT,{x:A.x+120,y:CLOSE_Y+20,z:AN.camera.dutch_zoom,r:AN.camera.dutch_angle});
  if(m==='push') Object.assign(camT,{x:960,y:560,z:1,r:0}); };
function springCam(dt){
  if(camMode==='push'){ camT.z=1+Math.min(AN.camera.push_max,(T-pushStart)*AN.camera.push_rate); }
  const w=2*Math.PI*AN.camera.spring_hz, z=AN.camera.spring_damp, n=3, h=dt/n;
  for(let i=0;i<n;i++) for(const q of ['x','y','z','r']){ camV[q]+=(-w*w*(cam[q]-camT[q])-2*z*w*camV[q])*h; cam[q]+=camV[q]*h; } }
function filmCam(dt){ if(camTw && camTw.custom) Object.assign(cam,camTw.custom(T)); else springCam(dt); keepInFrame(); }
// 画面永远不超出 1920×1080 的布景：倍率 ≥ 1（倾斜时留余量），取景框不出界
function keepInFrame(){ const zmin=1+1.8*Math.abs(cam.r)+(fx.shakeA||0)*2.2/1080;
  if(cam.z<zmin) cam.z=zmin; const hw=960/cam.z, hh=540/cam.z;
  cam.x=Math.max(hw,Math.min(1920-hw,cam.x)); cam.y=Math.max(hh,Math.min(1080-hh,cam.y)); }
function tween2(to,durA,over){ // 加速推进，冲过头一点再回稳
  const from={...cam}, t0=T; camTw={hold:true,t0,dur:durA+.32,custom:(t)=>{ const a=(t-t0)/durA;
    if(a<1){ const e=easeIn3(Math.max(0,a)); const o={}; for(const q of ['x','y','z','r']) o[q]=from[q]+(to[q]*(q==='z'?over:1)-from[q])*e; return o; }
    const b=Math.min(1,(t-t0-durA)/.32), e=easeOut3(b), o={...to}; o.z=to.z*over+(to.z-to.z*over)*e; return o; }}; }
// 推进大屏时前后景的视差
function parS(){ if(clipState==='off' && !camTw) return 1; return 1+Math.max(0,cam.z-1)*0.95; }
function charAlpha(){ const s=parS(); return Math.max(0,Math.min(1,1-(s*cam.z-3.0)/1.2)); }
function layerBegin(k){ const s=1+(parS()-1)*(k||1); ctx.save(); ctx.translate(cam.x,cam.y); ctx.scale(s,s); ctx.translate(-cam.x,-cam.y); }
function layerEnd(){ ctx.restore(); }

/* ---------- 大屏实机画面 ---------- */
var WALLR=SCENE.screen;                          // 放实机画面的屏幕区域（世界坐标，最好 16:9）
var WALLFULL=SCENE.screen_frame;                 // 放画面时整块变暗的区域
var WALLCAM={x:WALLR.x+WALLR.w/2,y:WALLR.y+WALLR.h/2,z:Math.max(1080/WALLR.h,1920/WALLR.w),r:0};   // 推进大屏后画面正好铺满
var wallOn=false, wallFlashT=-9, clipState='off', clipStateT=-9, curWin=null, CLIPIMG={};
function winAt(t){ for(const w of FILM.wins) if(t>=w.open && t<w.close+0.25) return w; return null; }
function winIn(t){ for(const w of FILM.wins) if(t>=w.open-0.001 && t<w.close-0.001) return w; return null; }
function segAt(w,t){ let s=w.segs[0]; for(const q of w.segs) if(t>=q.t) s=q; return s; }
function clipURL(t){ const w=winAt(t); if(!w) return null; const s=segAt(w,t);
  if(s.dir){ const n=Math.max(0,Math.min(s.n-1,Math.floor((t-s.t)*30))); return s.dir+'/'+String(n+1).padStart(5,'0')+'.jpg'; }
  return s.img; }
window.prepClip=async t=>{ const u=clipURL(t); if(!u || CLIPIMG[u]) return; const im=new Image(); im.src=u; try{ await im.decode(); }catch(e){} CLIPIMG[u]=im;
  const keys=Object.keys(CLIPIMG); if(keys.length>8) delete CLIPIMG[keys[0]]; };
function drawFootage(g,x,y,w,h,drift){   // 把当前这一帧实机画面等比铺满到 (x,y,w,h)，带黑边的素材先裁掉黑边
  const u=clipURL(T), im=u&&CLIPIMG[u]; if(!(im&&im.complete&&im.naturalWidth)) return false;
  const s=segAt(curWin||winAt(T),T); let zz=1, ox=0; if(drift && s && !s.dir){ const a=T-s.t; zz=1.04+a*.006; ox=Math.sin(a*.2)*8; }
  const [cx,cy,cw,ch]=(s&&s.crop)||[0,0,im.naturalWidth,im.naturalHeight], k=Math.max(w/cw,h/ch)*zz, dw=cw*k, dh=ch*k;
  g.save(); g.beginPath(); g.rect(x,y,w,h); g.clip(); g.imageSmoothingEnabled=true; g.drawImage(im,cx,cy,cw,ch,x+(w-dw)/2+ox,y+(h-dh)/2,dw,dh); g.restore(); return true; }
function drawWallClip(){
  if(!(wallOn && T-wallFlashT>.05)) return;
  ctx.fillStyle='#04060c'; ctx.fillRect(WALLFULL.x,WALLFULL.y,WALLFULL.w,WALLFULL.h);
  drawFootage(ctx,WALLR.x,WALLR.y,WALLR.w,WALLR.h,true); }
function openClip(){ KWS.forEach(k=>{ if(!k.out) k.out=T; }); clipState='opening'; clipStateT=T; wallOn=true; wallFlashT=T+AN.camera.wall_flash;
  PKG.event('screen_in'); tween2({...WALLCAM},AN.camera.wall_in,AN.camera.wall_overshoot); }
function closeClip(after){ KWS.forEach(k=>{ if(!k.out) k.out=T; }); clipState='closing'; clipStateT=T; wallFlashT=T; wallOn=false;
  const from={...cam}, t0=T+.06, to={x:960,y:540,z:1,r:0};
  camTw={hold:false,custom:(t)=>{ const OUT=AN.camera.wall_out, k=Math.max(0,Math.min(1,(t-t0)/OUT)), e=easeOut3(k), o={}; for(const q of ['x','y','z']) o[q]=from[q]+(to[q]-from[q])*e;
    o.r=(k>=1)? .022*Math.exp(-(t-t0-OUT)*5)*Math.sin((t-t0-OUT)*14) : 0;
    if(t-t0>1.4){ camTw=null; Object.assign(camT,to); for(const q in camV) camV[q]=0; } return o; }};
  camMode='wide'; Object.assign(camT,{x:960,y:540,z:1,r:0}); PKG.event('screen_out');
  setTimeout(()=>{ for(const c of [A,B]){ c.sk.jv-=AN.switch.land_jump; c.sk.s=-AN.switch.land_squash; } },640);   // 主播落地弹一下
  if(after && after!=='wide') setTimeout(()=>setCam(after),AN.camera.return_delay*1000); }

/* ---------- 主播贴纸：说话拉伸 + 换表情弹跳 ---------- */
var ANCH={A:(SHOW.hosts.A.anchors||{}),B:(SHOW.hosts.B.anchors||{})};
function bigMove(who,id){ const m=(SHOW.hosts[who].fxkind||{}); if(m[id]) return m[id]!=='soft';   // 大动作跳得高一点
  return /point|explain|fist|raise|wave|slam|surprised|angry|smug|sparkle|laugh|happy/.test(id); }
function stkGeom(c){ const inClip=clipState==='on'||clipState==='opening'&&cam.z>2; const rec=STKIMG[c.who][c.sk.cur];
  if(HK.on) return {x:c.who===HK.who?hookX(c.who):9999,base:HKC.base,h:HKC.h,rec,screen:true};
  if(inClip && c.who===CUR) return {x:CORNER.x,base:CORNER.base,h:CORNER.h,rec,screen:true};
  return {x:c.x,base:STUDIO.base,h:STUDIO.h,rec,screen:false}; }
// 贴纸上某一点（按人物范围的比例）在画面上的位置；包装层放粒子、漫符时用
function anchorPt(c,id,fx_,fy){ const G=stkGeom(c), r=G.rec; if(!r) return {x:c.x,y:STUDIO.base-STUDIO.h*.8,sc:1,screen:false}; const sc=G.h/r.h;
  const a=(ANCH[c.who][id])||[fx_,fy]; return {x:G.x+(r.bb.x0+(r.bb.x1-r.bb.x0)*a[0]-r.bb.cx)*sc, y:G.base-(r.bb.y1-(r.bb.y0+(r.bb.y1-r.bb.y0)*a[1]))*sc, sc:G.h/640, screen:G.screen}; }
setSticker=function(c,id){ if(!STKIMG[c.who][id]) return; const changed=c.sk.cur!==id; const k=c.sk; k.cur=id; k.s=-STK_TUNE.pop; k.v=0; k.rv+=(Math.random()<.5?-1:1)*(.15+Math.random()*.1);
  const big=bigMove(c.who,id); k.jv=(k.jv||0)-(big?AN.switch.jump_big:AN.switch.jump_small); if(changed && T>1) PKG.onSticker(c,id,big); };
stkUpdate=function(c,dt){   // 配音波形里每个字冒头 = 顶一下拉伸弹簧；换表情的跳跃是另一个弹簧
  const k=c.sk, w=2*Math.PI*STK_TUNE.freq, D=2*STK_TUNE.damp*w, Q=AN.talk; let imp=0;
  const lv=lipSample(c).level; k.slow=lerp(k.slow,lv,.08);
  if(T>k.refr && lv>Q.onset && lv-k.prevLv>Q.rise && lv>k.slow+.05){ imp=Q.kick+lv*Q.kick_lv; k.refr=T+Q.gap; } k.prevLv=lv;
  if(imp){ k.v+=imp*STK_TUNE.amp; k.rv+=(Math.random()-.5)*Q.tilt*imp; }
  const n=4, h=dt/n, wr=w*.8;
  for(let i=0;i<n;i++){ k.v+=(-w*w*k.s-D*k.v)*h; k.s+=k.v*h; k.rv+=(-wr*wr*k.r-2*.35*wr*k.rv)*h; k.r+=k.rv*h; }
  k.jy=k.jy||0; k.jv=k.jv||0; const wj=2*Math.PI*AN.switch.jump_hz; for(let i=0;i<n;i++){ k.jv+=(-wj*wj*k.jy-2*AN.switch.jump_damp*wj*k.jv)*h; k.jy+=k.jv*h; } };
function drawStickerAt(g,c,x,base,hgt){
  const rec=STKIMG[c.who][c.sk.cur]; if(!rec) return;
  const k=c.sk, sy=1+k.s+AN.talk.breath*Math.sin(T*2.1+(c.who==='B'?1.3:0)), sx=1-k.s*.6, sc=hgt/rec.h, jy=Math.min(0,(k.jy||0))*hgt/640;
  g.save(); g.translate(x,base+jy); g.rotate(k.r*c.face*1.3); g.scale(sx*sc,sy*sc); g.imageSmoothingEnabled=true; g.imageSmoothingQuality='high';
  g.drawImage(rec.img,-rec.bb.cx,-rec.bb.y1); g.restore(); }
drawStickerTo=(g,c)=>drawStickerAt(g,c,c.x,STUDIO.base,STUDIO.h);
// 大屏全屏时，正在说话的主播缩到右下角
var CORNER=Object.assign({x:1700,base:856,h:360},(SHOW.ui||{}).corner_host||{}), cornerK=0;
function drawCorner(){
  const want=(clipState==='on'||clipState==='opening'&&cam.z>2)?1:0; cornerK+=(want-cornerK)*.2;
  if(cornerK<.01 || HK.on) return; const c=CH[CUR], e=easeBack(Math.min(1,cornerK));
  const g=ctx; g.save(); g.setTransform(1,0,0,1,0,0); g.translate(CORNER.x,CORNER.base); g.scale(e,e); g.translate(-CORNER.x,-CORNER.base);
  drawStickerAt(g,c,CORNER.x,CORNER.base,CORNER.h); g.restore(); }

/* ---------- 特效：稿子里的【特效:xxx】只是一个事件，长什么样由 package.js 的 effect() 决定 ---------- */
function doFx(name,who){ PKG.effect(name,who); }

/* ---------- 信息牌（【信息牌:上行 · 下行】，只在大屏上出现） ---------- */
var badge=null, badgeT=0;
function drawBadge(){ if(!badge || clipState==='off') return; const bk=easeBack(Math.min(1,(T-badgeT)/.35))+elastic(T-badgeT)*.05;
  const g=ctx; g.save(); g.setTransform(1,0,0,1,0,0); g.translate(1560,150); g.scale(bk,bk);
  g.shadowColor='rgba(0,0,0,.3)'; g.shadowBlur=16; g.fillStyle='rgba(255,255,255,.95)'; rrect(g,-250,-52,500,104,22); g.fill(); g.shadowColor='transparent';
  const sunny=badge.includes('晴')&&!badge.includes('多云');
  g.fillStyle='#ffc23a'; g.beginPath(); g.arc(-185,-6,26,0,7); g.fill();
  g.strokeStyle='#ffc23a'; g.lineWidth=5; for(let i=0;i<8;i++){ const a=i*Math.PI/4+T; g.beginPath(); g.moveTo(-185+Math.cos(a)*33,-6+Math.sin(a)*33); g.lineTo(-185+Math.cos(a)*42,-6+Math.sin(a)*42); g.stroke(); }
  if(!sunny){ g.fillStyle='#b9c7dc'; for(const [x,y,r] of [[-172,12,18],[-150,4,22],[-128,14,16]]){ g.beginPath(); g.arc(x,y,r,0,7); g.fill(); } }
  const [t1,t2]=badge.split(' · '); g.textAlign='left'; g.textBaseline='middle';
  g.font=`700 24px ${UIF}`; g.fillStyle='#6a7590'; g.fillText(t1||'',-110,-22); g.font=`900 34px ${UIF}`; g.fillStyle='#123d9c'; g.fillText(t2||'',-110,18);
  g.restore(); }

/* ---------- 要点贴纸 ---------- */
var KWS=[], KWCOL={gold:['#ffcf3a','#ff9f1c'],pink:['#ff7aa8','#ff4f7b'],blue:['#4aa8ff','#2f6ef0'],mint:['#3fe0c5','#18a99c'],purple:['#a77bff','#7a4bf0'],red:['#ff6b5a','#e8293b']};
function starPath(g,r,k,inner){ g.beginPath(); for(let i=0;i<k*2;i++){ const a=i*Math.PI/k-Math.PI/2, rr=i%2?r*inner:r; g.lineTo(Math.cos(a)*rr,Math.sin(a)*rr); } g.closePath(); }
function addKW(who,text,col){ if(HK.on){ HKW.push({who,text,col,t0:T,slot:0,tilt:(HKW.length%2?1:-1)*.04,out:null}); return; }
  const mine=KWS.filter(k=>k.who===who && !k.out); if(mine.length>=UIC.keyword_max) mine[0].out=T;
  const used=new Set(KWS.filter(k=>!k.out).map(k=>k.slot)); let slot=0; while(used.has(slot)) slot++;
  KWS.push({who,text,col,t0:T,slot,tilt:(KWS.length%2?1:-1)*(.05+.03*Math.random()),out:null}); }
function kwAnchor(k){ const c=CH[k.who], inClip=clipState!=='off' && cam.z>1.9;
  if(inClip){ const y0=badge?300:180; return {x:1540,y:y0+k.slot*118}; }
  const side=c.who==='A'?-1:1, wx=c.x+side*300, wy=STUDIO.base-STUDIO.h*.94; const s=parS();
  let x=960+((wx-cam.x)*s)*cam.z, y=540+((wy-cam.y)*s)*cam.z+k.slot*118;
  return {x:Math.max(230,Math.min(1690,x)),y:Math.max(150,Math.min(720,y))}; }
function kwPill(g,k,x,y,align){ const a=T-k.t0, cs=KWCOL[k.col]||KWCOL.gold; let s=easeBack(Math.min(1,a/.26))+elastic(a)*.12; if(k.out!=null) s*=Math.max(0,1-easeIn3((T-k.out)/.25)); if(s<=0.01) return;
  g.save(); g.font=`900 46px ${UIF}`; const w=g.measureText(k.text).width+64, h=84; g.translate(align==='right'?x-w/2:x,y+Math.sin(a*5+(k.slot||0))*4);
  g.rotate((k.tilt||0)+Math.sin(a*14)*.06*Math.exp(-a*3)); g.scale(s,s*(1+elastic(a)*.05));
  g.shadowColor='rgba(10,20,50,.35)'; g.shadowBlur=18; g.shadowOffsetY=8; g.fillStyle='#ffffff'; rrect(g,-w/2-9,-h/2-9,w+18,h+18,30); g.fill(); g.shadowColor='transparent';
  const lg=g.createLinearGradient(0,-h/2,0,h/2); lg.addColorStop(0,cs[0]); lg.addColorStop(1,cs[1]); g.fillStyle=lg; rrect(g,-w/2,-h/2,w,h,24); g.fill();
  g.fillStyle='rgba(255,255,255,.28)'; rrect(g,-w/2+8,-h/2+6,w-16,h*.36,16); g.fill();
  g.textAlign='center'; g.textBaseline='middle'; g.lineWidth=9; g.lineJoin='round'; g.strokeStyle='rgba(20,30,70,.55)'; g.strokeText(k.text,0,3); g.fillStyle='#fff'; g.fillText(k.text,0,3);
  g.fillStyle='#fff6a8'; g.translate(w/2-4,-h/2+4); g.rotate(a*2); starPath(g,16,4,.35); g.fill();
  g.restore(); }
function drawKWs(){
  KWS=KWS.filter(k=>T>=k.t0 && (k.out==null || T-k.out<.25) && T-k.t0<UIC.keyword_hold+.3);
  for(const k of KWS){ if(T-k.t0>UIC.keyword_hold && !k.out) k.out=T; }
  const g=ctx; g.save(); g.setTransform(1,0,0,1,0,0);
  for(const k of KWS){ const P=kwAnchor(k); kwPill(g,k,P.x,P.y); }
  g.restore(); }

/* ---------- 板块转场：只记状态，画法在 package.js 的 sectionCard() ---------- */
var EYE=null, SECN=0;
function startEye(sec){ SECN++; const [big,small]=sec.split(' · '); EYE={t0:T,big,small:small||'',n:SECN}; PKG.event('section',EYE); }
function instantSetup(r){ KWS=[];   // 转场盖住画面的那一刻，把镜头和大屏直接摆到下一板块的开头状态
  const w=winIn(r.t0-0.12+0.002);
  if(w){ curWin=w; clipState='on'; clipStateT=T-5; wallOn=true; wallFlashT=-9; camTw={custom:()=>({...WALLCAM})}; Object.assign(cam,WALLCAM); }
  else { clipState='off'; wallOn=false; camTw=null; setCam(r.cam||'wide'); if(camMode==='push') camT.z=1; Object.assign(cam,camT); for(const q in camV) camV[q]=0; } }

/* ---------- 看点速报（开头的整屏冷开场）：只记状态，画法在 package.js 的 hook() ---------- */
var STING_T=EP.sting_t||0, HOOK_END=EP.hook_end==null?null:EP.hook_end, HOOK_TOTAL=EP.hook_total||0;
var HK={on:false,who:'A',prev:null,swapT:-9,line:null,lineT:-9,n:0,mode:'clip',bub:'',bubT:-9,bubEnd:-9,itemT:-9}, HKW=[];
(function(){ const f=FILM.lines.find(r=>r.hook); if(f){ HK.who=f.who; HK.mode=f.hookMode||'clip'; HK.n=f.hookN||1; HK.on=true; } })();
var HKC=Object.assign({x:1560,base:1150,h:900},(SHOW.ui||{}).hook_host||{});   // 看点速报里说话主播的位置
function hookActive(){ return HOOK_END!=null && T<HOOK_END+0.45; }
function hookX(who){ const k=Math.min(1,(T-HK.swapT)/.38);       // 换人：新的弹进来，旧的滑出去
  if(who===HK.who) return HKC.x+(1-easeBack(k))*620;
  if(who===HK.prev && k<1) return HKC.x+easeIn3(k)*700; return 9999; }
function hookLine(r){
  HK.on=true; HK.line=r; HK.lineT=T;
  if(HK.who!==r.who){ HK.prev=HK.who; HK.who=r.who; HK.swapT=T; }
  HK.bub=r.bubble||''; HK.bubT=T+.12; HK.bubEnd=r.t1+.25;
  if(r.hookMode!==HK.mode || (r.hookN && r.hookN!==HK.n)){ HK.itemT=T; HKW.forEach(k=>{ if(!k.out) k.out=T; }); }
  HK.mode=r.hookMode||'clip'; if(r.hookN) HK.n=r.hookN; }
function hookState(){   // 交给 package.js 的全部信息
  HKW=HKW.filter(k=>T>=k.t0 && (k.out==null||T-k.out<.25)); HKW.filter(k=>!k.out).forEach((k,i,arr)=>{ k.slot=arr.length-1-i; });
  return {who:HK.who, mode:HK.mode, n:HK.n, total:HOOK_TOTAL, title:EP.hook_title||'看点速报', bubble:HK.bub, bubbleOn:!!HK.bub && T>=HK.bubT && T<HK.bubEnd+.3,
    bubbleAge:T-HK.bubT, itemAge:Math.max(0,T-HK.itemT), sub:curSub(), keywords:HKW, start:T, end:HOOK_END, out:HOOK_END!=null&&T>HOOK_END?Math.min(1,(T-HOOK_END)/.42):0,
    hostX:w=>hookX(w), host:(g,w,x,base,h)=>drawStickerAt(g,CH[w],x,base,h), footage:(g,x,y,w,h)=>(HK.mode==='clip'?drawFootage(g,x,y,w,h,false):false), pill:kwPill, hostPos:HKC}; }

/* ---------- 事件表（时间由 pipeline.py stage 算好） ---------- */
var EV=[]; function ev(t,f){ EV.push({t,f}); }
FILM.lines.forEach((r,li)=>{
  const who=r.who, oth=who==='A'?'B':'A', t0=r.t0-0.12;
  const afterHook=HOOK_END!=null && !r.hook && li>0 && FILM.lines[li-1].hook;
  if(r.hook){ ev(t0,()=>{ CUR=who; hookLine(r); if(r.st) setSticker(CH[who],r.st); if(r.re) setSticker(CH[oth],r.re); (r.fx||[]).forEach(f=>doFx(f,who)); }); }
  else {
  if(r.sec && li>0 && !afterHook){ ev(r.t0-1.35,()=>startEye(r.sec)); ev(r.t0-0.85,()=>instantSetup(r)); }
  ev(t0,()=>{ CUR=who;
    if(r.sec) setSection(r.sec);
    const w=winIn(t0+0.002);
    if(w && (clipState==='off'||clipState==='closing')){ curWin=w; openClip(); }
    else if(!w && clipState!=='off' && clipState!=='closing'){ closeClip(r.cam); }
    else if(!w && r.cam && clipState==='off'){ setCam(r.cam); }
    if(r.st) setSticker(CH[who],r.st);
    if(r.re) setSticker(CH[oth],r.re);
    badge=r.badge||null; if(r.badge) badgeT=T;
    (r.fx||[]).forEach(f=>doFx(f,who));
  });
  }
  (r.atT||[]).forEach(([t,w,s])=>ev(t,()=>setSticker(CH[w],s)));
  (r.fxT||[]).forEach(([t,f])=>ev(t,()=>doFx(f,who)));
  (r.kwT||[]).forEach(([t,tx,col])=>ev(t,()=>addKW(who,tx,col)));
  if(r.closeT!=null) ev(r.closeT,()=>closeClip(r.camAfter));
  r.chunks.forEach((ch,ci)=>{
    ev(ch.t0,()=>{ const prev=SUBS[SUBS.length-1]; const same=prev && prev.who===who && T-(prev.lastEnd||0)<1.2;
      SUBS.forEach(s=>{ if(!s.outAt) s.outAt=T; }); if(same) SUBS=SUBS.filter(s=>s!==prev);
      SUBS.push({who,text:ch.text,t0:T,dur:999,noSlide:same,lastEnd:ch.t1}); });
    const nx=r.chunks[ci+1]?r.chunks[ci+1].t0:(FILM.lines[li+1]?FILM.lines[li+1].t0:FILM.end);
    if(nx-ch.t1>1.4) ev(ch.t1+.7,()=>{ SUBS.forEach(s=>{ if(!s.outAt) s.outAt=T; }); });
  });
});
ev(STING_T+0.05,()=>{ HK.on=false; KWS=[]; clipState='off'; wallOn=false; camTw=null; setCam('push'); Object.assign(cam,{x:960,y:540,z:1,r:0}); PKG.event('sting'); });
EV.sort((a,b)=>a.t-b.t); var evI=0;
function runEvents(){ while(evI<EV.length && EV[evI].t<=T){ EV[evI].f(); evI++; }
  if(clipState==='opening' && T-clipStateT>1) clipState='on';
  if(clipState==='closing' && T-clipStateT>1.05) clipState='off';
  SUBS=SUBS.filter(s=>!(s.outAt && T>s.outAt+.4)); }
