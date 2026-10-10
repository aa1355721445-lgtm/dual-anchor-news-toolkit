/* =====================================================================
   图片场景：用两张图拼一个演播室，不用写代码。
     背景图 background：主播身后的一切（墙、屏幕、地面），1920×1080 最好；比例不同会等比铺满裁边。
     前景图 foreground：挡在主播前面的东西（主播台），透明底 PNG，和背景同尺寸对齐；没有可以不放。
   在 show.json → scene 里写：
     "type": "image", "background": "背景.png", "foreground": "前景.png",
     "screen": {...}, "hosts": {...}       ← 用「场景编辑器.html」拖出来再复制进去
   可选：
     "screen_idle": "title"（默认，屏幕上显示节目标题动画）| "none"（就用背景图里画的屏幕）| "某张图.png"
     "overlay": "光效.png"   叠加在最上层的透明图（比如灯光、玻璃反光），会轻微呼吸
   想要会动的场景元素（闪灯、滚动字幕、跟着说话亮的灯），改用代码场景，参考 example.js。
   ===================================================================== */
(function(){
  let BG=null, FG=null, IDLE=null, OV=null;
  defineScene({
    name:'图片场景',
    async load(api){
      const C=api.cfg;
      BG=await api.image(C.background); FG=await api.image(C.foreground);
      if(C.screen_idle && !['title','none'].includes(C.screen_idle)) IDLE=await api.image(C.screen_idle);
      if(C.overlay) OV=await api.image(C.overlay);
      if(!BG) console.warn('图片场景：没有找到背景图 '+C.background);
    },
    back(g,t,api){
      if(BG) api.cover(g,BG,0,0,1920,1080); else { g.fillStyle='#1a2547'; g.fillRect(0,0,1920,1080); }
      const S=api.scene.screen, mode=api.cfg.screen_idle||'title';
      if(IDLE){ g.save(); g.beginPath(); g.rect(S.x,S.y,S.w,S.h); g.clip(); api.cover(g,IDLE,S.x,S.y,S.w,S.h); g.restore(); }
      else if(mode==='title') api.screenIdle(g,S,t);
    },
    front(g,t,api){
      if(FG) api.cover(g,FG,0,0,1920,1080);
      if(OV){ g.globalAlpha=.85+.15*Math.sin(t*1.3); g.globalCompositeOperation='screen'; api.cover(g,OV,0,0,1920,1080); g.globalAlpha=1; g.globalCompositeOperation='source-over'; }
    }
  });
})();
