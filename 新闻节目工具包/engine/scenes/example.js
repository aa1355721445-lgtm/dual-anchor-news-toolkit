/* =====================================================================
   示例演播室（纯代码绘制，不需要任何图片）
   这是一个「代码场景」的完整范例：想做自己的代码场景，复制这个文件改就行。
   规则见 docs/scene_rules.md。所有坐标都是 1920×1080 的世界坐标。

   defineScene({...}) 里可以写：
     screen        放实机画面的屏幕（建议 16:9）            {x,y,w,h}
     screen_frame  放画面时整块变暗的区域（可选，默认=screen）{x,y,w,h}
     hosts         主播站位：A/B 的 x、脚底线 base、贴纸高度 height、cut_y（可选，低于这条线的贴纸被裁掉）
     glow          灯光参考点 [x,y]（可选，给包装层做大屏泛光用，默认屏幕中心）
     palette       颜色表（show.json → scene.palette 可以覆盖）
     load(api)     载入图片等（可选，可以 async）
     back(g,t,api) 画主播身后的一切（墙、地面、屏幕待机画面……）
     front(g,t,api)画挡在主播前面的东西（主播台、话筒……），可选
   show.json → scene 里写的 screen / hosts / glow / palette 会覆盖这里的默认值。
   ===================================================================== */
defineScene({
  name:'示例演播室',
  screen:{x:560,y:118,w:800,h:450},
  screen_frame:{x:548,y:106,w:824,h:474},
  hosts:{A:{x:600},B:{x:1320},base:905,height:640},
  glow:[960,343],
  palette:{
    wall_top:'#121a33', wall_bottom:'#263866', ceiling:'#0b1124',
    strip:'#45e0d0', strip2:'#2f86f0',
    floor_top:'#1a2547', floor_bottom:'#0a0f22',
    desk:'#f4f6fa', desk_shade:'#b9c4d6', desk_edge:'#45e0d0', desk_label:'NEWS',
    screen_idle:'#1d3f8f', bezel:'#0a0f1e',
    side_head:'#e8293b', side_screens:['HOT','NEWS']
  },

  back(g,t,api){
    const P=api.pal, S=api.scene.screen, F=api.scene.screen_frame, HZ=700;
    // 墙
    let gr=g.createLinearGradient(0,0,0,HZ); gr.addColorStop(0,P.wall_top); gr.addColorStop(1,P.wall_bottom); g.fillStyle=gr; g.fillRect(0,0,1920,HZ);
    g.fillStyle='rgba(255,255,255,.035)'; for(let x=60;x<1920;x+=120) g.fillRect(x,70,2,HZ-70);
    // 天花板
    g.fillStyle=P.ceiling; g.fillRect(0,0,1920,70);
    for(let i=0;i<24;i++){ g.fillStyle='rgba(255,250,235,.35)'; g.fillRect(40+i*80,58,28,6); }
    // 竖条装饰：谁在说话谁那边的亮一点（演示 api.level 的用法）
    const lvA=api.level('A'), lvB=api.level('B');
    for(const [x,c,lv] of [[150,P.strip,lvA],[330,P.strip2,lvA],[1590,P.strip2,lvB],[1770,P.strip,lvB]]){
      g.fillStyle=api.rgb(api.hex(c),.45+lv*.5); g.fillRect(x-5,90,10,HZ-110); }
    // 两块竖屏（滚动的条目）
    (P.side_screens||[]).slice(0,2).forEach((label,i)=>{ const x=i?1612:148, y=170, w=160, h=380;
      g.fillStyle=P.bezel; api.rrect(g,x-8,y-8,w+16,h+16,10); g.fill();
      g.save(); g.beginPath(); g.rect(x,y,w,h); g.clip(); g.fillStyle='#f6f8fc'; g.fillRect(x,y,w,h);
      g.fillStyle=P.side_head; g.fillRect(x,y,w,52); g.fillStyle='#fff'; g.font=`900 30px ${UIF}`; g.textAlign='center'; g.textBaseline='middle'; g.fillText(label,x+w/2,y+27);
      const off=(t*26+i*40)%44; for(let r=0;r<10;r++){ const yy=y+66+r*44-off; if(yy<y+56) continue; g.fillStyle=r%4===1?'#f0b4b7':'#c9ced6'; g.fillRect(x+12,yy,(r*7+i*5)%3===0?100:126,12); g.fillStyle=P.side_head; g.fillRect(x+w-20,yy,8,12); }
      g.restore(); });
    // 大屏：外框 + 待机画面（放实机画面时引擎会盖在上面）
    g.fillStyle=P.bezel; api.rrect(g,F.x-10,F.y-10,F.w+20,F.h+20,16); g.fill();
    api.screenIdle(g,S,t);
    // 地面
    gr=g.createLinearGradient(0,HZ,0,1080); gr.addColorStop(0,P.floor_top); gr.addColorStop(1,P.floor_bottom); g.fillStyle=gr; g.fillRect(0,HZ,1920,1080-HZ);
    g.strokeStyle='rgba(255,255,255,.05)'; g.lineWidth=2; for(let i=-10;i<=10;i++){ g.beginPath(); g.moveTo(960+i*60,HZ); g.lineTo(960+i*260,1080); g.stroke(); }
        g.fillStyle=P.strip; g.fillRect(0,HZ-2,1920,3);
  },

  front(g,t,api){
    const P=api.pal, L=230, R=1690, cx=960, hw=(R-L)/2, top=x=>{ const u=(x-cx)/hw; return 830-30*u*u; };
    // 主播台正面
    g.beginPath(); g.moveTo(L,top(L)); for(let x=L;x<=R;x+=10) g.lineTo(x,top(x)); g.lineTo(R,1080); g.lineTo(L,1080); g.closePath();
    let gr=g.createLinearGradient(0,800,0,1080); gr.addColorStop(0,P.desk); gr.addColorStop(1,P.desk_shade); g.fillStyle=gr; g.fill();
    // 台面（亮边）和发光条
    g.lineWidth=10; g.strokeStyle='#ffffff'; g.beginPath(); for(let x=L;x<=R;x+=10) g.lineTo(x,top(x)); g.stroke();
    g.lineWidth=6; g.strokeStyle=P.desk_edge; g.beginPath(); for(let x=L+20;x<=R-20;x+=10) g.lineTo(x,top(x)+40); g.stroke();
    // 两侧阴影，让台子有弧度
    for(const [x0,x1] of [[L,L+260],[R,R-260]]){ const sg=g.createLinearGradient(x0,0,x1,0); sg.addColorStop(0,'rgba(40,50,80,.35)'); sg.addColorStop(1,'rgba(40,50,80,0)'); g.fillStyle=sg; g.fillRect(Math.min(x0,x1),790,260,290); }
    // 台标牌
    if(P.desk_label){ g.fillStyle=P.strip2; api.rrect(g,cx-70,836,140,40,10); g.fill(); g.fillStyle='#fff'; g.font=`900 26px ${UIF}`; g.textAlign='center'; g.textBaseline='middle'; g.fillText(P.desk_label,cx,857); }
    // 话筒
    for(const mx of [api.scene.hosts.A.x+170, api.scene.hosts.B.x-170]){ const y=top(mx);
      g.fillStyle='#2d3240'; g.fillRect(mx-4,y-60,8,60); g.fillRect(mx-22,y-6,44,8); g.fillStyle='#1d2029'; api.rrect(g,mx-12,y-92,24,40,10); g.fill(); g.fillStyle=P.side_head; g.fillRect(mx-12,y-60,24,4); }
  }
});
