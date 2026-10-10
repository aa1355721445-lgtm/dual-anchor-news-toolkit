/* =====================================================================
   包装层 package.js —— 节目「长什么样」的部分都在这里
   ---------------------------------------------------------------------
   通用版只给【素白占位】：白字黑底，能让流水线跑通出片，方便你看清每一层在什么时候出现。
   做你自己的节目时，把下面每个函数换成你的设计（台标、新闻栏、转场、片头、看点速报、灯光、特效）。
   每个函数的作用、什么时候被调用、能拿到哪些数据，见 docs/package_rules.md。

   能用的全局数据（只读）：
     T 当前秒数 · W/H 画面尺寸 1920×1080 · SHOW0 节目配置(show.json) · EP0 本期配置(episode.json)
     SPK.A / SPK.B 主播名字和颜色 · SUBS 字幕列表 / curSub() 当前字幕 · SECTION 当前栏目 / secT 换栏目的时刻
     TICKER 快讯数组 · clock() 节目时钟 · CUR 正在说话的主播 · clipState 大屏状态 off/opening/on/closing
     EYE 板块转场 {t0,big,small,n} · STING_T 片头时刻 · hookActive()/hookState() 看点速报
     anchorPt(CH.A,'',.5,.2) 主播头部在画面上的位置 · lipSample(CH.A).level 主播此刻音量 0–1
     cam 镜头 {x,y,z,r} · fx.shakeX/shakeY 可以写入它们做震屏 · fx.punch(.08) 镜头轻推
     window.STATION_IMG 台标图 · window.TITLE_IMG 节目标题图（节目包 品牌/ 里有才会有）
   ===================================================================== */
const PKG = (function(){
  const WHITE='#ffffff', DIM='rgba(0,0,0,.72)';
  const FXNAME={slam:'拍桌',flash:'闪光',lines:'速度线',punch:'冲击',sweat:'汗',sweatB:'汗',question:'问号',exclaim:'感叹',anger:'生气',blush:'脸红',sparkle:'闪亮'};
  let FXLOG=[];   // 占位：最近触发的特效，屏幕上标一行字
  const text=(g,s,x,y,size,align,col)=>{ g.font=`700 ${size}px ${UIF}`; g.textAlign=align||'left'; g.textBaseline='middle'; g.fillStyle=col||WHITE; g.fillText(s,x,y); };

  return {
    /* 载入你自己的包装素材（图片、字体……）。ld(路径) 返回 Image 或 null；素材放在节目包的 包装/ 文件夹会被拷到 pkg/ 下 */
    async load(ld){},

    /* —— 世界坐标层（跟着镜头推拉）—— */
    behindHosts(g,t){ /* 主播身后的灯光：光束、背光、大屏泛光……（通用版不画） */ },
    frontOfHosts(g,t){ /* 主播前面的粒子、漫符……（通用版不画） */ },

    /* —— 屏幕层（不跟镜头动），按下面的顺序一层层叠 —— */
    overlay(g,t){ /* 整屏的光斑、调色、暗角……（通用版不画） */ },

    logo(g,t){   // 左上角台标
      const S=window.STATION_IMG;
      if(S){ const h=50, w=h*S.width/S.height; g.drawImage(S,36,40,w,h); return; }
      const nm=(SHOW0.channel&&(SHOW0.channel.name||SHOW0.channel.lower_third_label))||SHOW0.show_name||'';
      if(nm){ g.font=`700 30px ${UIF}`; const w=g.measureText(nm).width+28; g.fillStyle=DIM; g.fillRect(36,40,w,48); text(g,nm,50,65,30); }
    },

    lowerThird(g,t){   // 下方新闻栏：栏目名 + 说话人 + 字幕（快讯 TICKER、时钟 clock() 通用版不显示）
      const y0=H-120;
      g.fillStyle=DIM; g.fillRect(0,y0,W,120);
      if(SECTION){ g.font=`700 26px ${UIF}`; const w=g.measureText(SECTION).width+32; g.fillStyle=DIM; g.fillRect(0,y0-44,w,44); text(g,SECTION,16,y0-22,26); }
      const s=curSub(); if(!s) return;
      const sp=SPK[s.who]; g.font=`700 44px ${UIF}`; const nm=sp.name+'：', nw=g.measureText(nm).width;
      text(g,nm,60,y0+60,44,'left',sp.c1||WHITE);
      const sz=fitText(g,s.text,W-120-nw,44,700); text(g,s.text,60+nw,y0+60,sz);
    },

    effects(g,t){   // 屏幕上的特效层。占位：把触发的特效名字标出来，提示「这里该有一个特效」
      FXLOG=FXLOG.filter(e=>T-e.t<1.2&&T>=e.t);
      FXLOG.forEach((e,i)=>{ const s=`【特效：${FXNAME[e.name]||e.name}】`; g.font=`700 30px ${UIF}`; const w=g.measureText(s).width+24;
        g.fillStyle=DIM; g.fillRect(W/2-w/2,120+i*50,w,42); text(g,s,W/2,141+i*50,30,'center'); });
    },

    sectionCard(g,t){   // 板块转场：EYE 出现后 1.45 秒；0.3–1.05 秒之间必须整屏盖住（镜头在这时换位、成片在这里切段）
      if(!EYE) return; const a=T-EYE.t0; if(a>1.45){ EYE=null; return; }
      const al=a<.25?a/.25:a>1.05?Math.max(0,1-(a-1.05)/.4):1;
      g.globalAlpha=al; g.fillStyle='#000'; g.fillRect(0,0,W,H);
      text(g,'PART '+String(EYE.n).padStart(2,'0'),W/2,400,32,'center','rgba(255,255,255,.6)');
      text(g,EYE.big,W/2,500,110,'center'); if(EYE.small) text(g,EYE.small,W/2,620,46,'center','rgba(255,255,255,.8)');
      g.globalAlpha=1;
    },

    hook(g,t){   // 看点速报（开头冷开场，整屏）。占位：左边实机画面框，右边说话的主播，气泡和字幕用白字
      if(!hookActive()) return; const S=hookState();
      g.globalAlpha=1-S.out;
      g.fillStyle='#0b0d14'; g.fillRect(0,0,W,H);
      text(g,S.title,60,80,56); if(S.total && S.mode!=='outro') text(g,`${S.n} / ${S.total}`,W-60,80,48,'right');
      const F={x:78,y:178,w:1104,h:621};
      g.fillStyle='#000'; g.fillRect(F.x,F.y,F.w,F.h); g.strokeStyle=WHITE; g.lineWidth=4; g.strokeRect(F.x,F.y,F.w,F.h);
      if(!S.footage(g,F.x,F.y,F.w,F.h)) text(g,S.mode==='outro'?((SHOW0.ui||{}).hook_outro||'精彩内容 · 请继续观看'):'？？？',F.x+F.w/2,F.y+F.h/2,S.mode==='outro'?56:160,'center');
      S.keywords.forEach(k=>S.pill(g,k,F.x+F.w-30,F.y+F.h-40-(k.slot||0)*104,'right'));
      for(const w of ['A','B']){ const x=S.hostX(w); if(x<2300) S.host(g,w,x,S.hostPos.base,S.hostPos.h); }
      if(S.bubbleOn){ g.font=`700 64px ${UIF}`; const bw=g.measureText(S.bubble).width+60, bx=S.hostX(S.who)-300-bw/2;
        g.fillStyle=WHITE; g.fillRect(bx,200,bw,100); text(g,S.bubble,bx+bw/2,250,64,'center','#000'); }
      g.fillStyle=DIM; g.fillRect(0,H-150,W,150);
      if(S.sub){ const sp=SPK[S.who], nm=sp.name+'：'; g.font=`700 52px ${UIF}`; const nw=g.measureText(nm).width; text(g,nm,60,H-75,52,'left',sp.c1||WHITE); const sz=fitText(g,S.sub.text,W-120-nw,52,700); text(g,S.sub.text,60+nw,H-75,sz); }
      g.globalAlpha=1;
    },

    sting(g,t){   // 片头标题：STING_T 开始 2.7 秒（有看点速报时紧接在它后面）
      if(!(T>=STING_T && T<STING_T+2.7)) return; const a=T-STING_T, al=a<.15?a/.15:a>2.3?Math.max(0,1-(a-2.3)/.4):1;
      g.globalAlpha=al; g.fillStyle='#000'; g.fillRect(0,0,W,H);
      const TI=window.TITLE_IMG; if(TI){ const tw=1000, th=tw*TI.height/TI.width; g.drawImage(TI,W/2-tw/2,H/2-60-th/2,tw,th); }
      else text(g,SHOW0.show_name||'',W/2,H/2-60,110,'center');
      if(EP0.sting_sub) text(g,EP0.sting_sub,W/2,H/2+120,44,'center','rgba(255,255,255,.85)');
      g.globalAlpha=1;
    },

    /* —— 事件：引擎在这些时刻通知你，可以在这里触发粒子、震屏、闪光 —— */
    effect(name,who){ FXLOG.push({name,who,t:T}); },   // 稿子里的【特效:xxx】：slam flash lines punch sweat question exclaim anger blush sparkle
    onSticker(c,id,big){},                              // 主播换表情的那一刻（big=大动作）
    event(name,data){}                                  // 'screen_in' 推进大屏 · 'screen_out' 拉回 · 'section' 板块转场开始 · 'sting' 片头开始
  };
})();
