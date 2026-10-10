# 配置：节目包（show.json）与每期（episode.json）

```
项目文件夹/
├─ 新闻节目工具包/        ← 本工具包（scripts、engine、templates、docs）
├─ 节目工具包打包/        ← 安装包存档（setup 自动整理）
├─ 工作区.json            ← setup 写的分区记录
├─ 节目包/                ← 一档节目一个，长期不变
│  ├─ show.json
│  ├─ 贴纸/               两位主播的贴纸（整张图）
│  ├─ 场景/               演播室场景用的图片或脚本（scene_rules.md）
│  ├─ 包装/               你自己的包装脚本和素材（package_rules.md，可选）
│  ├─ 品牌/               台标、节目标题图、游戏 logo（都可选）
│  ├─ 人物卡/             主播人设档案（写稿用），可放人物卡 JSON
│  └─ 术语对照.md          游戏内叫法 → 口播叫法
└─ 第1期/                 ← 每期一个（pipeline.py init 创建）
   ├─ episode.json
   ├─ 稿子_模板.md         （init 生成，已填好主播简称）
   ├─ 稿子.md
   ├─ 关键点汇总.md        （写稿依据）
   ├─ 原视频字幕.srt
   ├─ 原视频.mp4           （用户自己获取，可选：只在本机截片段时需要）
   ├─ 配音/  主播A.mp3 主播A.srt 主播B.mp3 主播B.srt
   ├─ 片段/  w00s0.mp4 …
   ├─ work/                流水线中间文件（可删）
   └─ 成片/                成片、封面、章节.txt
```

## 从模板开始（新节目第一次要做的）

安装包里的 `节目包/` 是空白模板。按这个顺序填：

1. **节目名和游戏**：`show_name`、`game`、`game_en`，`channel.lower_third_label`（频道名）。
2. **两位主播**：`hosts.A`（站左边）、`hosts.B`（站右边）的 `name`（字幕和配音文件名用）、`aliases`（稿子里每句开头的简称，例如 `["青"]` 就写 `青：……`）、`role`、`c1/c2`（名字颜色）、`sticker_prefix`（贴纸文件名前缀，英文）。
3. **表情表** `emotions`：写稿用的表情名 → 贴纸编号。模板里给了一套 12 个常用表情，按你的角色增删。`direction_words` 是「稿子括号里出现这个词就换这个表情」。
4. **人设**：`人物卡/主播人设档案.md` 照模板写两位主播的说话方式、口头禅、关系；有现成人物卡 JSON 的放进 `人物卡/`，在 `hosts.X.card` 写路径。
5. **场景**：先跑 `pipeline.py scene --show 节目包` 看示例演播室；想换成自己的见 scene_rules.md。
6. **贴纸**：可以先不画，渲染会用占位小人。写完第一期稿子后跑 `stickers`，照 `贴纸需求.md` 画。
7. **包装**：可以先用素白占位出片；想做自己的台标、新闻栏、转场、片头见 package_rules.md。
8. 跑 `setup`，看「节目包检查」里还剩什么。

## show.json

```jsonc
{
 "show_name": "节目名",                   // 大屏待机画面、片头、新闻栏的兜底文字
 "game": "游戏名", "game_en": "GAME NAME", // 封面大字 / 封面底部小字
 "format": "两位主播的新闻节目……",         // 写稿定位：谁负责什么、梗多不多
 "stickers_dir": "贴纸",
 "terms_file": "术语对照.md",
 "style_file": "人物卡/主播人设档案.md",
 "channel": {
  "name": "",                              // 没有台标图时左上角显示的文字（空就用 lower_third_label）
  "lower_third_label": "频道名",
  "station_logo": "品牌/station.png",      // 台标（可选）
  "title_art": "品牌/title.png",           // 节目标题图（可选）：大屏待机画面、片头
  "game_logo": "品牌/game_logo.png"        // 封面右上角（可选）
 },
 "scene": { "type": "example", … },       // 演播室场景，见 scene_rules.md
 "package": "包装/package.js",             // 可选：你自己的包装脚本；不写就用素白占位，见 package_rules.md
 "sections": ["开场 · 内容提要", "…"],     // 写稿参考的板块顺序
 "hosts": {
  "A": {
   "name": "主播A", "aliases": ["A"], "role": "主播",
   "card": "人物卡/xxx.json",              // 可选
   "sticker_prefix": "hostA",
   "default": "01_idle",                   // 默认表情
   "eyecatch": "08_smug",                  // 包装层可以用的「招牌表情」（转场、片头里露脸）
   "cover_sticker": "11_fist",             // 封面用的表情
   "c1": "#ff5d73", "c2": "#ff8a5b",       // 主播的代表色（字幕名字、占位小人）
   "glow": "255,80,110",                   // 主播的灯光色（RGB），给包装层做背光用
   "emotions": {"默认": "01_idle", "讲解": "02_explain", "…": "…"},
   "direction_words": {"叉腰": "得意", "…": "…"},
   "anchors": {"03_point": [0.85, 0.25]},  // 可选：贴纸上的「手」在哪（人物范围的比例），包装层放粒子用
   "fxkind": {"03_point": "big"}           // 可选：换到这张时算大动作（跳得高）还是 "soft"
  },
  "B": { "…": "…" }
 },
 "timing": {"gap_switch": 0.36, "gap_same": 0.42, "gap_interrupt": 0.14, "gap_section": 1.45, "gap_into_clip": 0.5, "start": 2.8, "tail": 2.4,
            "hook_start": 0.8, "gap_after_hook": 3.3},   // 对话节奏，见 staging_rules.md
 "audio": {"orig_level": 0.32, "orig_rule": "…", "sfx_level": 0.5},
 "animation": {"talk": {…}, "switch": {…}, "camera": {…}},   // 弹动和镜头手感，见 animation_rules.md
 "footage": {"fill_letterbox": true},      // 片段有黑边时自动裁掉铺满大屏
 "ui": {"subtitle_max_chars": 22, "keyword_max": 3, "keyword_hold": 2.9,
        "hook_sections": ["看点速报"], "hook_title": "看点速报", "hook_outro": "精彩内容 · 请继续观看",
        "corner_host": {"x": 1700, "base": 856, "h": 360},   // 大屏全屏时右下角小主播的位置（可选）
        "hook_host": {"x": 1560, "base": 1150, "h": 900}}    // 看点速报里主播的位置（可选，你的包装可以不用）
}
```

`ui` 里你自己的包装需要的参数也可以放这里（例如颜色、滚动速度），包装脚本里用 `SHOW0.ui.xxx` 读。

### 贴纸规格（整张图，不分部件）
- **一张贴纸 = 一个完整的角色图**：同一个人、同样的取景和大小，只是表情和动作不同。不分部件、不拼装，也不需要张嘴版、眨眼版——说话时程序让整张图做弹性拉伸，换表情时整张图压扁再弹起。
- 需要哪些由稿子决定：写完稿跑 `stickers`，列出这期要用的、已有的、要新画的，写成 `贴纸需求.md`。
- 透明底 PNG（白底或纯绿底也行，会自动抠），建议正方形、1000 像素以上，角色在画面下部居中，四周留一点空；同一位主播的所有贴纸画风、描边、大小一致。
- 各张贴纸身体位置不用对齐，程序按脚底自动摆放；贴纸在画面里多大由场景的 `hosts.height` 决定（整张图的高度，不是人物的高度）。
- 文件名：`<前缀>_<两位编号>_<英文名>.png`，例如 `hostA_03_point.png`。编号 + 英文名就是「贴纸编号」（`03_point`）。新画的放进贴纸文件夹，在 `emotions` 里加一行 `"表情名": "编号_英文名"`，稿子里就能写【贴纸:表情名】。
- 英文名里带这些词会被当成「大动作」（换上时跳得高一点）：point explain fist raise wave slam surprised angry smug sparkle laugh happy；不想按名字判断就在 `fxkind` 里指定。
- 没画的贴纸渲染时用占位小人（写着主播名和表情名），`qa` 会列出来。
- **不画官方角色**：主播贴纸由用户自己提供，工具包不生成。

### 品牌图（都可选）
台标、节目标题图、游戏 logo 都只是图片文件，换同名文件即可。缺哪张都能出片：没有台标显示频道名文字，没有标题图显示节目名文字，没有游戏 logo 封面右上空着。建议透明底 PNG；标题图横版约 3:1。

## 换游戏 / 换主播 / 换内容

| 换什么 | 做什么 |
|---|---|
| 同一游戏的下一期 | `init --ep <新文件夹> --show <节目包> --version 2.2`，填 episode.json |
| 同节目的其他内容（活动速报、PV 解读） | 新建一期；episode.json 改 `kind`、`section0`、`sting_sub`、封面文字；稿子自定板块。原视频没有字幕时 `source_srt` 留空 |
| 换游戏 | 复制一份节目包，改 `game`、`game_en`、品牌图、`术语对照.md`、`sections`；世界观资料写进人设档案 |
| 换主播 | 改 `hosts.A/B` 的全部字段、贴纸、人设；只支持两位主播同框 |
| 换演播室 | 改 `scene`（scene_rules.md） |
| 换包装 | 改 `package` 指向的脚本（package_rules.md） |

## episode.json（每期）

`init` 从 `templates/episode.example.json` 生成，**生成后要逐项改成本期内容**（`doctor --ep` 会提醒还有 XX 占位）。

| 字段 | 意思 |
|---|---|
| `show_dir` | 节目包相对本期文件夹的路径（init 的 `--show` 自动填） |
| `version` | 版本号，封面用；不是版本内容就留空 `""` |
| `title` / `kind` | 本期名 / 内容类型，只给人看 |
| `date` | 节目时钟起点（`YYYY-MM-DD HH:MM`），包装层可以显示 |
| `section0` | 第一个板块之前的栏目名 |
| `sting_sub` | 片头标题下面那行字 |
| `ticker` | 滚动快讯（4–6 条短句），包装层可以显示 |
| `script` | 稿子文件名，默认 `稿子.md` |
| `source_video` | 原视频，给 `clips --cut` 用 |
| `source_video_win` / `clips_dir_win` | Windows 完整路径，给 `截片段.ps1` 用 |
| `source_srt` | 原视频字幕，给 `speechmap` 用；没有就留空 |
| `voice.A/B.audio` / `.srt` | 每位主播的配音和配音字幕（init 按主播名预填） |
| `clips_dir` | 截好的片段放哪，默认 `片段` |
| `split_mb` | 成片超过这个大小就按板块切段；本机填 0 不切 |
| `output_name` | 成片文件名（不含扩展名） |
| `cover.*` | 封面文字：`kicker` 左上标签、`special` 英文小字、`sub` 副标题、`hot_index` 第几个字红底、`ver_label`、`info` 信息行、`gift`/`gift_note` 福利字、`foot` 底部小字 |
| `cover.bg_clip` + `cover.bg_frame` | 封面背景用哪个片段的第几帧；或 `cover.bg_image` 直接给图 |
| `cover.sticker_A` / `cover.sticker_B` | 可选：封面用的贴纸编号 |

## work/ 文件夹

流水线中间文件：script.json、timeline.json、film.json、master.wav、site/（渲染网页 + 片段帧）、frames/（成片帧）。会到 1–3GB，交付后可以删。
