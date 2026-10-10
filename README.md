# 双主播新闻节目工具包（通用版）

将游戏官方前瞻、活动速报和 PV 等素材制作成「两位主播 + 演播室」形式的资讯节目。包含 Python 流水线、浏览器画面引擎、渲染脚本、规则文档和节目配置模板。

## 快速导航

- [原始使用说明](使用说明.md)
- [完整流水线说明](新闻节目工具包/docs/流水线完整说明.md)
- [流程图 HTML](新闻节目工具包/docs/流程图.html)（下载后用浏览器打开）
- [技能说明](新闻节目工具包/SKILL.md)
- [节目配置说明](新闻节目工具包/docs/config.md)
- [节目配置模板](节目包/show.json)
- [每期配置模板](新闻节目工具包/templates/episode.example.json)
- [稿子模板](新闻节目工具包/templates/稿子模板.md)

## 目录结构

```text
dual-anchor-news-toolkit/
├─ README.md
├─ 使用说明.md
├─ 新闻节目工具包/
│  ├─ SKILL.md
│  ├─ docs/          规则、工作流和配置说明
│  ├─ engine/        画面引擎、示例场景和场景编辑器
│  ├─ scripts/       Python 流水线与 Node.js 渲染脚本
│  └─ templates/     每期配置、稿子和封面模板
└─ 节目包/           主播、品牌、场景和包装配置模板
```

外层目录使用英文小写和短横线，内部保留压缩包的中文目录与相对路径。原始 38 个文件保持原样；复制或下载时请保留完整目录结构。

## 下载与环境

在本仓库页面选择 **Code → Download ZIP**，解压后进入项目根目录。也可以克隆本仓库后进入 `dual-anchor-news-toolkit/` 目录。

需要 Python 3.9 以上、Node.js 18 以上，以及已加入 PATH 的 FFmpeg / FFprobe。Python 依赖为 NumPy 和 Pillow；Node.js 依赖由 `新闻节目工具包/scripts/package.json` 声明。渲染使用 Playwright Chromium，并需要可显示中文的字体。

在本目录运行：

```powershell
python "新闻节目工具包/scripts/pipeline.py" setup --install
```

该命令会检查节目包和环境，并按需要安装 Python 依赖、Playwright 及 Chromium。FFmpeg 和 Node.js 需提前准备；详细操作见原始使用说明。

如果希望分别安装依赖：

```powershell
python -m pip install -r "新闻节目工具包/scripts/requirements.txt"
Push-Location "新闻节目工具包/scripts"
npm install
npx playwright install chromium
Pop-Location
```

## 开始制作

1. 编辑 `节目包/show.json`，填写节目名、游戏名与两位主播信息。
2. 按节目包各目录的说明准备贴纸、场景、品牌和包装素材。
3. 初始化第一期：

   ```powershell
   python "新闻节目工具包/scripts/pipeline.py" init --ep "第1期" --show "节目包" --version "2.1"
   ```

4. 按[工作流](新闻节目工具包/docs/workflow.md)准备素材、写稿、配音、排时间线、渲染和检查。

通用模板自带示例场景和占位显示，正式节目所需的主播形象、品牌图片与包装需自行准备。

## 仓库维护

`.gitignore` 排除依赖目录、缓存、每期工作目录、配音、片段、成片和本机工作区记录。节目模板及其贴纸、场景、品牌和包装资产仍可正常纳入 Git。

本目录归档自 `双主播新闻节目工具包_通用版.zip`。压缩包未附许可证，因此本次归档未自行添加开源许可。
