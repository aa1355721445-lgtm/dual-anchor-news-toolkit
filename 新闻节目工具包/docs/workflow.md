# 完整工作流（从找视频到成片）

命令都是 `python3 <工具包>/scripts/pipeline.py <命令> --ep <本期文件夹>`（Windows 用 `python`）。下文简写成 `pipeline <命令>`。
**脚本路径和 `--ep` 都写绝对路径**，就不用管当前目录在哪。

常用参数：
| 参数 | 用在 | 作用 |
|---|---|---|
| `--show <节目包>` | init | 本期用哪个节目包 |
| `--version 1.6` | init | 把模板里的版本号换掉 |
| `--in a.json[,b.json]` | bsub | B 站字幕 JSON |
| `--cut` | clips | 不生成脚本，直接用本机 ffmpeg 截片段 |
| `--stills 1.5,30,95` | render | 只截这几个时间点的图（每张约 20 秒） |
| `--range 60,90` | render | 渲染这一段并出带声音的预览 mp4（帧会留在 work/frames） |
| `--keep` | render | 全片渲染时保留已有帧，只补缺的（中断后续渲） |
| `--workers N` | render | 渲染进程数，默认 = CPU 核数（最多 4） |
| `--port N` | render | 本地网页服务端口，默认 8765，被占用会自动换 |
| `--tag v2` | encode / cover | 改版时文件名加后缀，不覆盖旧文件 |
| `--crf --preset --maxrate` | encode | 画质/码率（默认 25 / veryfast / 1.6M，6 分钟约 60MB） |
| `--force` | align | 有句子对不上时跳过它们继续 |

## 初始化（第一次用、换电脑、收到新安装包时）

一条命令把工作区理顺：
```
python <工具包>/scripts/pipeline.py setup [--root <项目文件夹>] [--install] [--update]
```
它会依次做：
1. **找安装包并解压**：在项目文件夹（和下一层子文件夹）里找含 `新闻节目工具包/`、`节目包/` 的压缩包（比如 `双主播新闻节目工具包_通用版.zip`），把里面的文件解压到项目文件夹，多个包自动合并；放在项目文件夹根目录的安装包随后挪进 `节目工具包打包/` 存档。
   - 已经存在的文件不覆盖。工具包出了新版时加 `--update`，只更新 `新闻节目工具包/` 里的工具；**`节目包/` 里的资产和配置永远不会被覆盖**。
   - 节目包里不小心删掉的文件，再跑一次会从安装包里补回来。
2. **列出工作区分区**：工具包、节目包、每期文件夹、安装包存档，以及工具不使用的其他文件夹。
3. **检查运行环境**：python 库、ffmpeg、Node.js、playwright、chromium、中文字体；加 `--install` 自动装 python 库和 playwright（ffmpeg、Node.js 要自己装，会给出安装命令）。
4. **检查节目包**：show.json 能否读、节目名是不是还是占位、表情表里每个贴纸文件在不在（缺的列出来，渲染先用占位小人）、场景配置和图片、包装脚本（还在用素白占位会提示）、品牌图、人设档案、术语对照。
5. **写 `工作区.json`**：记下各分区路径和检查结果。
6. **列出还缺什么**和下一步该运行的命令（还没有任何一期时，给出看场景预览和新建第 1 期的完整命令）。

只有压缩包、还没解压过时：先把压缩包解压到项目文件夹（或让 Claude 解压），再运行 `setup`。

**Claude 的做法**：第一次接手、或者用户说「装一下 / 初始化 / 看看还缺什么」时，先跑 `setup`，把输出整理成几句话告诉用户：工作区分成了哪几块、还缺什么、哪些能自动补（直接补）、哪些要用户动手（给出具体操作）。

### 工作区分区

```
项目文件夹/
├─ 新闻节目工具包/    工具（可整体升级替换）
├─ 节目包/            这档节目的资产和配置（用户维护，工具不会覆盖）
├─ 节目工具包打包/    安装包存档
├─ 第1期/            每期一个文件夹（init 创建）
├─ 工作区.json        setup 写的分区记录
└─ 其他文件夹          工具不碰
```

## 节目只做一次：主播、场景、包装

新节目的节目包是模板，先把这几样定下来（详见 config.md「从模板开始」）：
1. show.json 里的节目名、两位主播（名字、简称、颜色、表情表）。
2. 场景：`pipeline scene --show <节目包>` 出 `场景预览.jpg`；要换成自己的布景见 scene_rules.md（`scene --export` 导出分层图 → 绘图软件里改 → 场景编辑器对位置）。
3. 包装：素白占位就能出片；做自己的台标、新闻栏、转场、片头、看点速报、灯光、特效见 package_rules.md。
4. 贴纸：可以等第一期稿子写完、跑 `stickers` 拿到需求清单再画。

## 零、先决定在哪里跑

**优先本机，本机不行再走云端。** 开工时先试一次本机。

| | 本机（用户电脑） | 云端（工作区） |
|---|---|---|
| 怎么判断能用 | 有能在用户电脑上执行命令的 shell，且 `pipeline doctor` 全绿 | 总是能用 |
| 文件 | 直接读写项目文件夹 | 用文件桥：从电脑拷入单文件 ≤400MB；写回单文件 ≤30MB、每次 ≤50 个/100MB |
| 原视频 | 直接截片段（`pipeline clips --cut`） | 原视频通常 >400MB 拷不进来 → 生成 `截片段.ps1` 让用户在本机跑 |
| 成片 | 一个完整文件（`split_mb: 0`） | 按板块切成 ≤29MB 的几段（`split_mb: 29`） |
| 依赖 | Python 3.9+（numpy、pillow）、ffmpeg、Node 18+；在 `scripts/` 里 `npm install` + `npx playwright install chromium` | 一般都有；`pipeline doctor` 检查 |

本机的 shell 起不来（报 workspace unavailable 之类）就别反复重试，直接走云端，并告诉用户一句。
云端模式的做法：把工具包、节目包、本期文件夹（不含原视频）拷进工作区同样的目录结构，跑完把 `成片/` 和需要的中间文件写回本期文件夹。

## 一、十个步骤

| # | 步骤 | 谁做 | 命令 / 文档 | 产出 |
|---|---|---|---|---|
| 1 | 找到目标视频 | Claude（浏览器） | sourcing_bilibili.md §1 | BV 号、标题、时长 |
| 2 | 拿字幕 | Claude（浏览器） | §2，`pipeline bsub` | 原视频字幕.srt |
| 3 | 截图核对 | Claude（浏览器） | §3 | 截图 |
| 4 | 关键点汇总 | Claude | §4，`pipeline speechmap` | 关键点汇总.md（事实 + 时间点 + 可留原声的时段） |
| 5 | 写稿 | Claude | script_format.md（开头先写「看点速报」，见第六节），`pipeline parse`；可从 `templates/稿子模板.md` 起手 | 稿子.md |
| 5b | 贴纸需求 | Claude | `pipeline stickers` | 贴纸需求.md（这期要用的表情/动作，哪些要新画；整张图，不分部件） |
| ⏸ | **用户审稿** | 用户 | 讨论梗位、配队建议、删改；需要时照贴纸需求画新贴纸 | 定稿、新贴纸 |
| 6 | 配音稿 | Claude | `pipeline dub` | 配音稿/<主播名>_配音稿.txt（无标识、数字已转汉字） |
| ⏸ | **用户配音** | 用户（外部 TTS / 真人） | 每人一条完整音频 + 导出 srt | 配音/*.mp3 *.srt |
| 7 | 排时间线 + 分镜 | Claude | `pipeline align`、`pipeline stage` | work/timeline.json、film.json |
| 8 | 截片段 | 本机：Claude；云端：用户 | `pipeline clips`（生成脚本和清单）/ `pipeline clips --cut` | 片段/w00s0.mp4 … |
| 9 | 渲染成片 | Claude | `pipeline prepclips` → `audio` → `render` → `encode` | 成片/*.mp4、章节.txt |
| 10 | 封面 + 检查 | Claude | `pipeline cover`、`pipeline qa`、qa_checklist.md | 封面_16x9.png、封面_4x3.png |

新建一期：`pipeline init --ep <项目文件夹>/第1期 --show <项目文件夹>/节目包 --version 2.1`，然后按提示把 `episode.json` 里的占位（XX、日期、快讯、封面文字）改成本期内容；本期文件夹里的 `稿子_模板.md` 已经填好主播简称，复制成 `稿子.md` 开写。`pipeline doctor --ep <本期>` 会列出还缺的素材。

### 注意顺序
- 第 7 步要在截片段之前：片段的编号（w00s0…）和每段要截多长，都是排完时间线才知道的。
- 稿子改了台词 → 必须重新 `dub` 并让用户重配改动的句子（或整条重配），否则 align 会报找不到。只删句子、只改标记不用重配。
- `dub` 还会生成 `配音稿/对话顺序对照.md`（两人台词按播出顺序排的表），给配音的人对照语气用。
- 片段截好以后再改 🎬，编号可能整体错位：重跑 `stage` → `clips`，对照新清单重截。

## 二、截片段（第 8 步）细节

`pipeline clips` 会在本期文件夹生成：
- `截片段.ps1`：Windows PowerShell（UTF-8 BOM，中文路径不乱码）。用户右键「用 PowerShell 运行」，或在 PowerShell 里 `powershell -ExecutionPolicy Bypass -File 截片段.ps1`。需要 ffmpeg 在 PATH 里。
- `截片段.sh`：Linux / mac。
- `截片段清单.md`：编号、开始时间、时长、是否留原声。

每段：从开始时间起截「需要时长 + 2.5 秒」，缩放并补边到 1280×720，H.264 + AAC（**保留声音**，成片里用不用原声由稿子决定）。
`episode.json` 里的 `source_video_win` / `clips_dir_win` 是给 ps1 用的 Windows 路径。

截好后：`pipeline prepclips` 拆帧和音轨，并把帧目录写回 film.json。缺片段会提示，大屏显示黑底。

## 三、渲染（第 9 步）

```
pipeline prepclips --ep X
pipeline audio --ep X
pipeline render --ep X --stills 1.5,30,95,200     # 先截几张看看（每张约 20 秒）
pipeline render --ep X --range 60,90              # 可选：30 秒带声音预览 work/preview_60_90.mp4
pipeline render --ep X                            # 全片（会先清空 work/frames）
pipeline encode --ep X                            # 帧不全会拒绝编码并告诉你缺哪
pipeline cover --ep X
pipeline qa --ep X                                # 必须在全片渲染之后跑
```
- 截图挑时间点：`work/film.json` 里 `wins[].open/close` 是进出大屏的时间，`lines[]` 里带 `sec` 的句子 `t0` 前 1.3 秒左右是板块转场。
- 速度参考（2 核、3 个进程）：约 9 帧/秒，6 分钟成片 ≈ 19 分钟；机器上同时有别的渲染会慢很多。`prepclips` 拆帧 6 分钟成片约 1–4 分钟，`work/` 会到 1–2GB（云端不要往回拷 work/）。
- 渲染是确定性的逐帧截图（虚拟时钟）。中途断了：`render --keep` 只补缺的帧，然后 `encode`。
- 长任务放后台跑，定期看进度，别干等。
- 只改了声音：`audio` → `encode`，不用重渲。

## 四、交付

- 本机：成片、封面、章节都在本期 `成片/` 里，告诉用户位置。
- 云端：把 `成片/` 里的文件写回用户电脑的本期文件夹（单文件 ≤30MB，所以要分段）；同时发到对话里。
- 交付时一句话说明：成片几段/多长、章节、哪些地方需要用户后期补（BGM、配队建议等）。
- 版本号：同一期改版时 `encode --tag v2`、`cover --tag v2`，不要覆盖用户可能开着的旧文件（写回电脑时覆盖会失败）。

## 五、需要停下来问用户的时刻

- 稿子写完（必须）。
- 关键点有歧义（字幕和画面对不上、数字不确定）。
- 原视频里没有合适的「无讲解」片段，原声要不要放宽。
- 用户的新要求和本文档规则冲突（例如想要 PV 音乐）——照用户说的做，并问要不要写进 show.json 作为新默认。
