# 素材获取：B 站找视频、拿字幕、截图

云端工作区连不上 B 站，**所有 B 站操作都在浏览器里做**（优先用户设置的浏览器；需要用户已登录 B 站，AI 字幕必须登录才能拿）。
不使用任何第三方下载站。视频文件由用户自己下载放进本期文件夹（需要截片段时）。

## 1. 找到目标视频

在 bilibili.com 的任意页面里，用 javascript 工具执行（带上登录 cookie）：

```js
// 在游戏官方账号的投稿里搜关键词。MID 换成官方账号的 uid（打开官方号主页，网址里 space.bilibili.com/ 后面那串数字）
const MID = 0, KW = '游戏名 前瞻';
const r = await fetch('https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=' +
  encodeURIComponent(KW) + '&order=pubdate', {credentials:'include'}).then(r=>r.json());
r.data.result.filter(v => v.mid === MID).slice(0,5)
  .map(v => ({bvid:v.bvid, title:v.title.replace(/<[^>]+>/g,''), pubdate:new Date(v.pubdate*1000).toISOString(), duration:v.duration}));
```
- 前瞻：官方号最新一条前瞻节目（或它的回顾版，回顾版通常有字幕）。活动速报 / 角色 PV：按用户给的标题或链接。把官方号 uid 和常用关键词记进 show.json 的 `format` 或人设档案，下次直接用。
- 用户直接给了链接就跳过搜索。
- 拿不准是不是最新一期，看官方动态（space.bilibili.com/<mid>/dynamic）确认下一期是否已经播出。
- 搜索接口被风控时，直接打开 `https://space.bilibili.com/<mid>/video` 读页面。

## 2. 字幕 → 原视频字幕.srt

```js
const bvid='BV...';
const v = await fetch(`https://api.bilibili.com/x/web-interface/view?bvid=${bvid}`,{credentials:'include'}).then(r=>r.json());
const cid = v.data.cid;   // 多 P 视频看 v.data.pages
const p = await fetch(`https://api.bilibili.com/x/player/wbi/v2?bvid=${bvid}&cid=${cid}`,{credentials:'include'}).then(r=>r.json());
p.data.subtitle.subtitles.map(s=>({lan:s.lan, url:s.subtitle_url}));   // 空数组 = 没登录或没字幕
// 取 ai-zh / zh-CN：
const sub = await fetch('https:' + p.data.subtitle.subtitles[0].subtitle_url).then(r=>r.json());
JSON.stringify(sub.body.map(x=>[x.from, x.to, x.content]));   // 存成 json 文件后：pipeline.py bsub --ep <本期> --in sub.json
```
- 返回值单次上限约 250KB，长字幕分两三次取（`slice`）。
- 在工作区里把 `[from,to,content]` 转成 SRT 存为本期 `原视频字幕.srt`。
- `wbi/v2` 报签名错误时换 `https://api.bilibili.com/x/player/v2?bvid=..&cid=..`。
- **没有字幕文件**：倍速播放视频，在画面底部约 88%–97% 高度截字幕条，去重后拼成长图读出来（慢，尽量避免）。

## 3. 截图（核对用 + 关键点汇总配图）

```js
const pu = await fetch(`https://api.bilibili.com/x/player/wbi/playurl?bvid=${bvid}&cid=${cid}&qn=64&fnval=16`,{credentials:'include'}).then(r=>r.json());
const vs = pu.data.dash.video.filter(x => /avc/.test(x.codecs));   // 选 avc
const el = document.createElement('video'); el.crossOrigin='anonymous'; el.muted=true; el.src = vs[0].baseUrl; document.body.append(el);
// 截一帧：
async function grab(t){ el.currentTime=t; await new Promise(r=>el.onseeked=r);
  const c=document.createElement('canvas'); c.width=1600; c.height=900; c.getContext('2d').drawImage(el,0,0,1600,900);
  return c.toDataURL('image/webp',0.8); }
```
- 单次 seek 约 8–15 秒一张；要连续截很多张时改成 2–3 倍速播放、边播边截。
- 每张 1600 宽 WebP，控制在 ~124KB 以内，每次只回传 1–2 张（250KB 上限）。
- 时间点按字幕内容挑：数字、日期、角色名、卡池图、福利图出现的画面。

## 4. 关键点汇总（关键点汇总.md）

- 用字幕 + 截图逐条核对专有名词（AI 字幕同音错字很多，以画面文字为准）。
- 按节目板块整理：每条写「事实 + 原视频时间点 + 截图」。时间点就是后面写 🎬 的依据。
- 记下原视频里**哪些时段没有讲解**（可留原声的候选）：本期文件夹放好 `原视频字幕.srt` 后跑 `pipeline.py speechmap`。
- 把新出现的游戏术语补进节目包的 `术语对照.md`。

## 5. 原视频文件

- 截片段需要原视频。用户自己下载（官方渠道 / 客户端缓存导出），放进本期文件夹，名字写进 episode.json 的 `source_video`。
- 本机可用时直接在本机截；云端只能读 ≤400MB 的单个文件，原视频一般超过，所以**截片段这一步通常在本机做**（见 workflow.md）。
