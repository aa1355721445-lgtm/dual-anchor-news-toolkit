#!/usr/bin/env python3
"""双主播新闻节目视频流水线（两位主播的整张贴纸 + 可自定义的演播室场景）。

用法:  python3 pipeline.py <命令> --ep <本期文件夹> [参数]
命令按顺序:
  setup       第一次用 / 换电脑：解压安装包、检查工作区分区、环境、节目包，列出还缺什么  (--root --install --update)
  doctor      检查环境（python 库 / ffmpeg / node + playwright）
  scene       预览节目包的演播室场景（不需要任何一期素材）-> <节目包>/场景预览.jpg  (--show；--export 导出分层 PNG)
  init        新建本期文件夹和 episode.json 模板          (--show <节目包文件夹>)
  parse       解析稿子（稿子.md）-> work/script.json，报告标记问题
  stickers    按稿子列出要用的表情/动作贴纸，缺的写进 贴纸需求.md（整张图，不分部件）
  dub         生成每位主播的配音稿 txt（无任何标识，数字转汉字）
  bsub        B 站字幕 JSON -> 原视频字幕.srt              (--in a.json[,b.json])
  speechmap   用原视频字幕查「哪些时间段没有官方讲解」，并检查稿子里标了原声的片段
  align       对齐配音（波形 + 配音字幕），排对话时间线 -> work/timeline.json
  stage       按规则补全分镜，生成渲染数据 -> work/film.json
  clips       生成截片段清单与命令（或 --cut 直接用本机 ffmpeg 截）
  prepclips   把截好的片段拆成帧和音轨
  audio       合成音效 + 原声垫底 + 配音 -> work/master.wav
  render      逐帧渲染 (--workers N, --range 秒,秒 预览, --stills t1,t2 截图)
  encode      编码成片，按板块切成 <= split_mb 的若干段，输出章节时间点
  cover       生成 16:9 与 4:3 封面
  qa          自检：音频重叠、素材缺失、关键时刻截图拼图
  all         align -> stage -> prepclips -> audio -> render -> encode -> cover -> qa
"""
import argparse, json, os, re, shutil, subprocess, sys, glob, wave, difflib, math, time
HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from textnorm import to_spoken, norm, phrases
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK and choke on ✔/⚠
    try: _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

SR = 48000
FPS = 30


# ------------------------------------------------------------------ config
def load_json(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def save_json(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


class Ctx:
    def __init__(self, ep_dir):
        self.ep_dir = os.path.abspath(ep_dir)
        self.ep = load_json(os.path.join(self.ep_dir, 'episode.json'))
        sd = self.ep.get('show_dir', '../节目包')
        self.show_dir = os.path.abspath(os.path.join(self.ep_dir, sd))
        self.show = load_json(os.path.join(self.show_dir, 'show.json'))
        self.work = os.path.join(self.ep_dir, 'work')
        os.makedirs(self.work, exist_ok=True)

    def p(self, rel):  # path relative to episode folder
        return rel if os.path.isabs(rel) else os.path.join(self.ep_dir, rel)

    def sp(self, rel):  # path relative to show folder
        return rel if os.path.isabs(rel) else os.path.join(self.show_dir, rel)

    def host_of(self, label):
        for k, h in self.show['hosts'].items():
            if label == h['name'] or label in h.get('aliases', []):
                return k
        return None


def sh(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        raise SystemExit('命令失败: ' + ' '.join(map(str, cmd)))
    return r


# ------------------------------------------------------------------ doctor / init
def env_check(quiet=False):
    """Check python libs / ffmpeg / node / playwright / chromium / fonts. Returns (ok, [(name, fix_cmd)])."""
    say = (lambda *x: None) if quiet else print
    ok, fixes = True, []
    for mod in ['numpy', 'PIL']:
        try:
            __import__(mod); say('✔ python', mod)
        except Exception:
            ok = False; say('✘ python', mod); fixes.append(('python 库 numpy/pillow', f'"{sys.executable}" -m pip install numpy pillow'))
    for b in ['ffmpeg', 'ffprobe', 'node']:
        has = bool(shutil.which(b)); say(('✔ ' if has else '✘ ') + b); ok &= has
        if not has:
            fixes.append((b, '装 ffmpeg 并加入 PATH（Windows: winget install Gyan.FFmpeg）' if b != 'node' else '装 Node.js 18 以上（Windows: winget install OpenJS.NodeJS.LTS）'))
    r = subprocess.run(['node', '-e', "require('playwright');console.log('ok')"], capture_output=True, text=True, cwd=HERE) if shutil.which('node') else None
    if r and r.returncode == 0:
        say('✔ node playwright')
        r2 = subprocess.run(['node', '-e', "const {chromium}=require('playwright');chromium.launch().then(b=>{console.log('ok');b.close()}).catch(e=>{console.log('FAIL '+e.message);process.exit(1)})"], capture_output=True, text=True, cwd=HERE)
        say(('✔ ' if r2.returncode == 0 else '✘ ') + 'chromium 能启动'); ok &= r2.returncode == 0
        if r2.returncode: fixes.append(('chromium', f'在 {HERE} 里运行 npx playwright install chromium'))
    else:
        ok = False; say('✘ node playwright')
        if shutil.which('node'): fixes.append(('playwright', f'在 {HERE} 里运行 npm install，再运行 npx playwright install chromium'))
    fonts = subprocess.run(['fc-list', ':lang=zh'], capture_output=True, text=True).stdout if shutil.which('fc-list') else ''
    say(('✔ ' if fonts.strip() or os.name == 'nt' else '? ') + '中文字体' + ('' if fonts.strip() or os.name == 'nt' else '（Linux 请装 fonts-noto-cjk）'))
    return ok, fixes


def cmd_doctor(a):
    ok, fixes = env_check()
    for n, f in fixes: print(f'  → {n}: {f}')
    print('\n环境' + ('就绪' if ok else '还缺东西，按上面提示安装'))
    if a.ep and os.path.exists(os.path.join(a.ep, 'episode.json')):
        c = Ctx(a.ep); miss = []
        if 'XX' in json.dumps(c.ep, ensure_ascii=False): miss.append('episode.json 里还有 XX 占位')
        if not os.path.exists(c.p(c.ep.get('script', '稿子.md'))): miss.append('稿子：' + c.ep.get('script', '稿子.md'))
        for k, v in c.ep.get('voice', {}).items():
            for kk in ('audio', 'srt'):
                if v.get(kk) and not os.path.exists(c.p(v[kk])): miss.append(f"{c.show['hosts'][k]['name']} 的配音{'字幕' if kk == 'srt' else ''}：{v[kk]}")
        for k, h in c.show['hosts'].items():
            if not glob.glob(os.path.join(c.sp(c.show['stickers_dir']), h['sticker_prefix'] + '_*.png')): miss.append(f"{h['name']} 的贴纸（{h['sticker_prefix']}_*.png；没有时渲染会用占位图）")
        for x in check_scene(c.show_dir, c.show): miss.append('场景：' + x)
        for key in ('station_logo', 'title_art', 'game_logo'):
            v = c.show.get('channel', {}).get(key)
            if v and not os.path.exists(c.sp(v)): miss.append(f'品牌图 {key}: {v}')
        print('\n本期素材：' + ('齐了' if not miss else '还缺（没到那一步可以先不管）：'))
        for m in miss: print('  -', m)


# ------------------------------------------------------------------ setup (first-run guide)
WS_FILE = '工作区.json'


def scene_paths(show_dir, show):
    """Where the scene script and its files are. Returns (type, script_path, assets_dir)."""
    sc = show.get('scene') or {}
    t = sc.get('type', 'example')
    if t == 'image':
        return t, os.path.join(KIT, 'engine', 'scenes', 'image.js'), os.path.join(show_dir, sc.get('dir', '场景'))
    if t == 'code':
        sp = os.path.join(show_dir, sc.get('script', '场景/scene.js'))
        return t, sp, os.path.dirname(sp)
    return 'example', os.path.join(KIT, 'engine', 'scenes', 'example.js'), None


def check_scene(show_dir, show):
    """Problems with the scene block of show.json (empty = fine)."""
    probs = []; sc = show.get('scene') or {}
    t, script, adir = scene_paths(show_dir, show)
    if sc.get('type', 'example') not in ('example', 'image', 'code'): probs.append(f"scene.type 只能是 example / image / code，现在是 {sc.get('type')}")
    if not os.path.exists(script): probs.append(f'找不到场景脚本 {script}')
    if t == 'image':
        if not sc.get('background'): probs.append('图片场景要在 scene.background 写背景图文件名')
        for k in ('background', 'foreground', 'overlay', 'screen_idle'):
            v = sc.get(k)
            if v and k == 'screen_idle' and v in ('title', 'none'): continue
            if v and not os.path.exists(os.path.join(adir, v)): probs.append(f'场景图片不在：{os.path.join(os.path.basename(adir), v)}')
    r = sc.get('screen')
    if r:
        if any(k not in r for k in 'xywh'): probs.append('scene.screen 要有 x y w h 四个数')
        elif abs(r['w'] / max(1, r['h']) - 16 / 9) > 0.08: probs.append(f"scene.screen 不是 16:9（{r['w']}×{r['h']}），实机画面会被裁边铺满")
    return probs


def check_show(show_dir):
    """Check a 节目包 folder. Returns list of problems (empty = complete). Lines containing 不影响出片 are advisory."""
    probs = []
    sj = os.path.join(show_dir, 'show.json')
    if not os.path.exists(sj): return ['没有 show.json']
    try: show = load_json(sj)
    except Exception as e: return [f'show.json 格式错误：{e}']
    if '{' in show.get('show_name', '{') or show.get('show_name', '').startswith('节目名'): probs.append('show.json 里节目名还是占位（show_name）')
    sd = os.path.join(show_dir, show.get('stickers_dir', '贴纸'))
    for k, h in show.get('hosts', {}).items():
        nm = h.get('name', k)
        for f in ('name', 'sticker_prefix', 'emotions'):
            if f not in h: probs.append(f'{nm}：show.json 缺 {f}')
        pre = h.get('sticker_prefix', '')
        have = {os.path.basename(x)[len(pre) + 1:-4] for x in glob.glob(os.path.join(sd, pre + '_*.png'))}
        need = set(h.get('emotions', {}).values()) | {h.get(x) for x in ('default', 'eyecatch', 'cover_sticker') if h.get(x)}
        lack = sorted(need - have)
        if lack and not have: probs.append(f'{nm}：还没有贴纸，要画 {len(lack)} 张：' + '、'.join(f'{pre}_{x}.png' for x in lack) + '（没画之前渲染用占位图）')
        elif lack: probs.append(f'{nm}：缺贴纸 ' + '、'.join(f'{pre}_{x}.png' for x in lack) + '（表情表里用到了；没画之前用占位图）')
        card = h.get('card')
        if card and not os.path.exists(os.path.join(show_dir, card)): probs.append(f'{nm}：缺人物卡 {card}')
    pk, _ = package_paths(show_dir, show)
    if not os.path.exists(pk): probs.append(f'找不到包装脚本 {show.get("package")}（show.json → package）')
    elif not show.get('package'): probs.append('包装用的是通用版素白占位（台标、新闻栏、转场、片头、看点速报都是白字黑底；不影响出片，做自己的见 docs/package_rules.md）')
    for key, v in show.get('channel', {}).items():
        if key in ('station_logo', 'title_art', 'game_logo') and v and not os.path.exists(os.path.join(show_dir, v)):
            probs.append(f'缺品牌图 {v}（不影响出片，会用文字代替）')
    for key in ('terms_file', 'style_file'):
        v = show.get(key)
        if v and not os.path.exists(os.path.join(show_dir, v)): probs.append(f'缺 {v}（写稿时要用）')
    probs += ['场景：' + x for x in check_scene(show_dir, show)]
    return probs


def zname(info):
    """Real file name inside a zip: zips made without the UTF-8 flag store raw bytes (UTF-8 on Linux/mac, GBK on Chinese Windows)."""
    n = info.filename
    if info.flag_bits & 0x800: return n
    raw = n.encode('cp437', errors='replace')
    for enc in ('utf-8', 'gbk'):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return n


def cmd_setup(a):
    """First-run guide: find the workspace, unpack the package zips into it, check environment + show pack, write 工作区.json."""
    import zipfile
    root = os.path.abspath(a.root or os.path.dirname(KIT))
    print(f'工作区：{root}\n')
    # 1) unpack package zips found in the workspace
    archive = os.path.join(root, '节目工具包打包')
    zips = []
    for z in glob.glob(os.path.join(root, '*.zip')) + glob.glob(os.path.join(root, '*', '*.zip')):
        try:
            with zipfile.ZipFile(z) as zf:
                names = [zname(i) for i in zf.infolist()]
        except Exception:
            continue
        if any(n.startswith(('新闻节目工具包/', '节目包/')) for n in names): zips.append(z)
    added = skipped = updated = 0
    for z in sorted(zips):
        with zipfile.ZipFile(z) as zf:
            for info in zf.infolist():
                n = zname(info)
                if n.endswith('/') or not n.startswith(('新闻节目工具包/', '节目包/', '使用说明.md')): continue
                dst = os.path.join(root, *n.split('/'))
                if os.path.exists(dst):
                    # tool code may be upgraded with --update; the show pack (your assets) is never overwritten
                    if a.update and n.startswith(('新闻节目工具包/', '使用说明.md')):
                        if open(dst, 'rb').read() != zf.read(info):
                            open(dst, 'wb').write(zf.read(info)); updated += 1
                    elif open(dst, 'rb').read() != zf.read(info):
                        skipped += 1          # differs from the package: keep the user's file
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, 'wb').write(zf.read(info)); added += 1
        if os.path.dirname(os.path.abspath(z)) == root:      # tidy: keep install zips in one place
            os.makedirs(archive, exist_ok=True)
            tgt = os.path.join(archive, os.path.basename(z))
            if not os.path.exists(tgt): shutil.move(z, tgt)
    if zips:
        if not added and not updated: print(f'① 安装包：找到 {len(zips)} 个，里面的文件都已经在工作区了')
        else: print(f'① 安装包：找到 {len(zips)} 个，解压新文件 {added} 个' + (f'，更新工具 {updated} 个' if updated else '') +
              (f'，有 {skipped} 个文件和安装包里的不一样、保留了你现在的' if skipped else '') + ('（工具包有新版时加 --update 覆盖工具；节目包里的资产永远不覆盖）' if skipped and not a.update else ''))
    else:
        print('① 安装包：工作区里没有找到节目工具包的压缩包（已经解压过就不用管）')
    # 2) workspace layout
    kit = os.path.join(root, '新闻节目工具包'); show = os.path.join(root, '节目包')
    if not os.path.isdir(kit): kit = KIT
    shows = [d for d in glob.glob(os.path.join(root, '*')) if os.path.exists(os.path.join(d, 'show.json'))]
    if os.path.isdir(show) and show not in shows: shows.insert(0, show)
    eps = sorted(d for d in glob.glob(os.path.join(root, '*')) if os.path.exists(os.path.join(d, 'episode.json')))
    print('\n② 工作区分区：')
    print(f'  工具包      {os.path.relpath(kit, root) if kit.startswith(root) else kit}')
    print('  节目包      ' + ('、'.join(os.path.basename(x) for x in shows) if shows else '✘ 没有（需要 show.json，贴纸、场景、品牌图可以后补；照 docs/config.md 新建）'))
    print('  每期文件夹  ' + ('、'.join(os.path.basename(x) for x in eps) if eps else '还没有（用 init 新建）'))
    print(f'  安装包存档  {os.path.basename(archive)}' + ('' if os.path.isdir(archive) else '（没有）'))
    known = {os.path.abspath(x) for x in [kit, archive] + shows + eps}
    other = [os.path.basename(d) for d in glob.glob(os.path.join(root, '*')) if os.path.isdir(d) and os.path.abspath(d) not in known]
    if other: print('  其他文件夹  ' + '、'.join(other) + '（工具不使用，留着无妨）')
    # 3) environment
    print('\n③ 运行环境：')
    ok, fixes = env_check()
    if fixes and a.install:
        names = [n for n, _ in fixes]
        if any('python' in n for n in names):
            print('  安装 python 库 …'); subprocess.run([sys.executable, '-m', 'pip', 'install', 'numpy', 'pillow'])
        if 'playwright' in names:
            print('  安装 playwright …'); subprocess.run('npm install', shell=True, cwd=HERE)
        if 'playwright' in names or 'chromium' in names:
            print('  安装渲染用浏览器 …'); subprocess.run('npx playwright install chromium', shell=True, cwd=HERE)
        ok, fixes = env_check(quiet=True)
        print('  装完复查：' + ('环境就绪 ✔' if ok else '还有没装好的，见下面「还缺」'))
    # 4) show pack
    print('\n④ 节目包检查：')
    show_probs = {}
    for sdir in shows:
        pr = check_show(sdir); show_probs[sdir] = pr
        print(f'  {os.path.basename(sdir)}：' + ('✔ 完整' if not pr else f'{len(pr)} 个问题'))
        for x in pr: print('    -', x)
    # 5) record the workspace
    ws = {'root': root, 'toolkit': kit, 'shows': shows, 'episodes': eps, 'archive': archive,
          'env_ok': ok, 'checked_at': time.strftime('%Y-%m-%d %H:%M')}
    save_json(os.path.join(root, WS_FILE), ws)
    # 6) what is still missing + next step
    todo = [f'{n}：{f}' for n, f in fixes] + [f'{os.path.basename(k)}：{x}' for k, v in show_probs.items() for x in v if '不影响出片' not in x]
    if not shows: todo.append('准备节目包')
    print('\n⑤ 还缺：' + ('没有了 ✔' if not todo else ''))
    for t in todo: print('  -', t)
    if fixes and not a.install: print('  （加 --install 可以自动装 python 库和 playwright；ffmpeg、Node.js 要自己装）')
    py = 'python' if os.name == 'nt' else 'python3'
    print('\n⑥ 下一步：')
    if not eps:
        print(f'  先看看场景：{py} "{os.path.join(kit, "scripts", "pipeline.py")}" scene --show "{shows[0] if shows else os.path.join(root, "节目包")}"（出 场景预览.jpg；想换场景见 docs/scene_rules.md）')
        print(f'  新建一期：{py} "{os.path.join(kit, "scripts", "pipeline.py")}" init --ep "{os.path.join(root, "第1期")}" --show "{shows[0] if shows else os.path.join(root, "节目包")}" --version 1.0')
    else:
        print(f'  继续做某一期：{py} "{os.path.join(kit, "scripts", "pipeline.py")}" doctor --ep "<那期的文件夹>"')
    print(f'  工作区信息已写入 {WS_FILE}；流程见 新闻节目工具包/docs/workflow.md，流程图见 docs/流程图.html')


def cmd_init(a):
    ep = os.path.abspath(a.ep)
    os.makedirs(ep, exist_ok=True)
    for d in ['配音', '片段', 'work', '成片']:
        os.makedirs(os.path.join(ep, d), exist_ok=True)
    tpl = load_json(os.path.join(KIT, 'templates', 'episode.example.json'))
    if a.show:
        tpl['show_dir'] = os.path.relpath(os.path.abspath(a.show), ep)
    show = None
    sdir = os.path.abspath(a.show) if a.show else os.path.abspath(os.path.join(ep, tpl.get('show_dir', '../节目包')))
    if os.path.exists(os.path.join(sdir, 'show.json')): show = load_json(os.path.join(sdir, 'show.json'))
    ver = a.version or 'X.X'
    sub = {'X.X': ver, '{节目名}': (show or {}).get('show_name', '节目名'), '{游戏}': (show or {}).get('game', '游戏名'), '{GAME}': (show or {}).get('game_en', 'GAME')}
    js = json.dumps(tpl, ensure_ascii=False)
    for k, v in sub.items(): js = js.replace(k, v)
    tpl = json.loads(js); tpl['version'] = ver
    if show:
        tpl['voice'] = {k: {'audio': f"配音/{h['name']}.mp3", 'srt': f"配音/{h['name']}.srt"} for k, h in show['hosts'].items()}
    if os.name == 'nt':
        tpl['source_video_win'] = os.path.join(ep, '原视频.mp4'); tpl['clips_dir_win'] = os.path.join(ep, '片段')
    else:
        tpl['source_video_win'] = ''; tpl['clips_dir_win'] = ''
    tpl['date'] = time.strftime('%Y-%m-%d') + ' 20:00'
    dst = os.path.join(ep, 'episode.json')
    if not os.path.exists(dst):
        save_json(dst, tpl)
    # a script skeleton with this show's host names filled in
    st = os.path.join(ep, '稿子_模板.md')
    if not os.path.exists(st):
        md = open(os.path.join(KIT, 'templates', '稿子模板.md'), encoding='utf-8').read()
        if show:
            for k, h in show['hosts'].items():
                md = md.replace('{' + k + '}', (h.get('aliases') or [h['name']])[0]).replace('{' + k + '名}', h['name'])
        for k, v in sub.items(): md = md.replace(k, v)
        open(st, 'w', encoding='utf-8').write(md)
    print('已创建', ep, '（附 稿子_模板.md：写稿时复制成 稿子.md）')
    print('下一步：打开 episode.json，把这些占位改成本期内容：title / section0 / sting_sub / ticker / output_name / cover（XX 都要换掉）；'
          '\n  date = 节目画面里的时钟（一般填前瞻播出日期）；原视频在用户电脑上时填 source_video_win（Windows 完整路径）；'
          '\n  要切段交付时 split_mb 填单文件上限（MB），本机填 0。然后照 稿子_模板.md 写 稿子.md。')


# ------------------------------------------------------------------ parse script
TAG = re.compile(r'【([^】:：]+)(?:[:：]([^】]*))?】')
CAM = {'全景': 'wide', '特写': 'SPK', '倾斜': 'dutch', '推近': 'push'}   # plus 特写<主播名/简称> = close-up on that host
FX = {'拍桌': 'slam', '闪光': 'flash', '速度线': 'lines', '冲击': 'punch', '汗': 'sweat', '问号': 'question',
      '感叹': 'exclaim', '生气': 'anger', '脸红': 'blush', '闪亮': 'sparkle'}
STOP_HEAD = re.compile(r'^#+\s*(术语|待讨论|附录|备注)')


def parse_clip(s):
    """🎬 18:33–18:47 原声 → 37:17@锚点 原声 ...   /  🎬 续   /  🎬 关"""
    s = s.strip().lstrip('🎬').strip()
    if s.startswith('续'):
        return {'keep': True}
    if s.startswith('关') or s.startswith('无'):
        return {'off': True}
    segs = []
    for part in re.split(r'\s*→\s*', s):
        m = re.match(r'(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*[–\-~]\s*(\d{1,2}):(\d{2})(?::(\d{2}))?)?(?:@(\S+))?(.*)', part.strip())
        if not m:
            continue
        g = m.groups()
        if g[2]:
            st = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2])
        else:
            st = int(g[0]) * 60 + int(g[1])
        en = None
        if g[3]:
            en = (int(g[3]) * 3600 + int(g[4]) * 60 + int(g[5])) if g[5] else int(g[3]) * 60 + int(g[4])
        rest = g[7] or ''
        segs.append({'src': st, 'src_end': en, 'anchor': g[6], 'orig': '原声' in rest, 'note': rest.replace('原声', '').strip()})
    return {'segs': segs} if segs else None


def cmd_parse(a, quiet=False):
    c = Ctx(a.ep)
    path = c.p(c.ep.get('script', '稿子.md'))
    lines, warn = [], []
    sec, clip, part = None, None, None
    hook_names = c.show.get('ui', {}).get('hook_sections', ['看点速报'])
    for raw in open(path, encoding='utf-8'):
        s = raw.strip()
        if STOP_HEAD.match(s):
            break
        if not s or s.startswith('>') or s.startswith('|') or s.startswith('---') or s.startswith('- ') or s.startswith('<!--'):
            continue
        if s.startswith('## ') or s.startswith('### '):
            t = re.sub(r'^#+\s*', '', s)
            t = re.sub(r'^\d+(-\d+)?[.、]\s*', '', t)
            t = re.sub(r'[（(][^）)]*[）)]\s*$', '', t).strip()
            if s.startswith('## '):
                sec = t
            continue
        if s.startswith('#'):
            continue
        if s.startswith('🎬'):
            clip = parse_clip(s)
            if clip is None:
                warn.append(f'看不懂的片段标记: {s}')
            continue
        if re.fullmatch(r'【[^】]*待讨论[^】]*】', s) or re.fullmatch(r'【[^】]*(配队建议|梗位)[^】]*】', s):
            continue
        m = re.match(r'^\*{0,2}([^\s*：:]{1,8})\*{0,2}[：:]\s*(.*)$', s)
        if not m:
            if lines and not s.startswith('【'):
                lines[-1]['raw'] += s       # continuation line
            continue
        who = c.host_of(m.group(1))
        if not who:
            warn.append(f'不认识的说话人「{m.group(1)}」: {s[:30]}')
            continue
        if sec: part = sec
        lines.append({'who': who, 'raw': m.group(2), 'sec': sec, 'clip': clip, 'part': part})
        sec, clip = None, None
    out = []
    for i, L in enumerate(lines):
        raw = L['raw']
        tags, dirs, spoken, pos_tags = [], [], '', []
        # walk the line keeping char offsets of mid-line tags (offset in spoken text)
        k = 0
        while k < len(raw):
            ch = raw[k]
            if ch == '【':
                j = raw.find('】', k)
                if j < 0:
                    spoken += raw[k:]; break
                mt = TAG.fullmatch(raw[k:j + 1])
                if mt:
                    key, val = mt.group(1).strip(), (mt.group(2) or '').strip()
                    if '@' in key and not val:      # 【收屏@锚点】 == 【收屏:锚点】
                        key, val = [x.strip() for x in key.split('@', 1)]
                    pos_tags.append((len(spoken), key, val))
                k = j + 1; continue
            if ch in '（(':
                j = raw.find('）' if ch == '（' else ')', k)
                if j < 0:
                    j = len(raw) - 1
                dirs.append((len(spoken), raw[k + 1:j]))
                k = j + 1; continue
            spoken += ch; k += 1
        spoken = re.sub(r'\*\*', '', spoken).strip()
        rec = {'i': i + 1, 'who': L['who'], 'text': spoken, 'spoken': to_spoken(spoken), 'sec': L['sec'], 'clip': L['clip'],
               'hook': bool(L['part']) and L['part'].split(' · ')[0].strip() in hook_names,
               'tags': [], 'dirs': dirs}
        for off, key, val in pos_tags:
            rec['tags'].append({'off': off, 'key': key, 'val': val, 'start': off == 0 or not spoken[:off].strip()})
        if not spoken:
            rec['silent'] = True
        out.append(rec)
    # validation
    emo = {k: set(h.get('emotions', {}).keys()) for k, h in c.show['hosts'].items()}
    for r in out:
        for t in r['tags']:
            if t['key'] in ('贴纸', '反应'):
                who = r['who'] if t['key'] == '贴纸' else ('B' if r['who'] == 'A' else 'A')
                if t['val'] not in emo[who] and not re.match(r'^\d+_\w+$', t['val']):
                    warn.append(f"第{r['i']}句 {t['key']}「{t['val']}」不在 {c.show['hosts'][who]['name']} 的表情表里（要新画的话跑 stickers 出需求清单）")
            elif t['key'] == '镜头' and t['val'] not in CAM and not (t['val'].startswith('特写') and c.host_of(t['val'][2:])):
                warn.append(f"第{r['i']}句 镜头「{t['val']}」应为 {'/'.join(CAM)} 或 特写+主播名")
            elif t['key'] == '特效' and any(x not in FX for x in re.split(r'[、,，+ ]+', t['val']) if x):
                warn.append(f"第{r['i']}句 特效「{t['val']}」应为 {'/'.join(FX)}")
            elif t['key'] not in ('贴纸', '反应', '镜头', '特效', '要点', '天气', '信息牌', '独奏', '收屏', '配队建议', '梗位', '气泡', '收尾'):
                warn.append(f"第{r['i']}句 不认识的标记【{t['key']}】")
        # anchors must exist in the spoken line, otherwise stage silently falls back
        def has(anc):
            return bool(anc) and (anc in r['text'] or norm(anc) in norm(r['text']))
        for t in r['tags']:
            if t['key'] == '要点' and '@' in t['val']:
                anc = t['val'].split('|')[0].split('@', 1)[1].strip()
                if not has(anc): warn.append(f"第{r['i']}句 要点锚点「{anc}」在台词里找不到（会退回到标记所在位置弹出）")
            if t['key'] == '收屏':
                if not t['val']: warn.append(f"第{r['i']}句 【收屏】缺锚点，写成【收屏@台词里的几个字】")
                elif not has(t['val']): warn.append(f"第{r['i']}句 收屏锚点「{t['val']}」在台词里找不到（会在句首收屏）")
                if not (r['clip'] and (r['clip'].get('segs') or r['clip'].get('keep'))):
                    warn.append(f"第{r['i']}句 【收屏】只能用在大屏上的句子（这句前面要有 🎬）")
        for k2, sg in enumerate((r['clip'] or {}).get('segs', [])):
            if k2 and sg.get('anchor') and not has(sg['anchor']):
                warn.append(f"第{r['i']}句 🎬 换画面的锚点「{sg['anchor']}」在台词里找不到（会按平均时长切换）")
            if k2 and not sg.get('anchor'):
                warn.append(f"第{r['i']}句 🎬 第{k2+1}个画面没写 @锚点（会按平均时长切换）")
    save_json(os.path.join(c.work, 'script.json'), {'lines': out, 'warnings': warn})
    if not quiet:
        n = {'A': 0, 'B': 0}
        for r in out:
            n[r['who']] += 0 if r.get('silent') else 1
        ns = sum(1 for r in out if r.get('silent'))
        print(f"共 {len(out)} 句：{c.show['hosts']['A']['name']} {n['A']} 句，{c.show['hosts']['B']['name']} {n['B']} 句" + (f"，只有动作没台词 {ns} 句" if ns else '') + "；"
              f"板块 {sum(1 for r in out if r['sec'])} 个；片段 {sum(1 for r in out if r['clip'] and r['clip'].get('segs'))} 处")
        for w in warn:
            print('⚠', w)
    return out


# ------------------------------------------------------------------ sticker needs
def cmd_stickers(a):
    """按稿子列出每位主播要用到的表情/动作贴纸：哪些已有、哪些要新画。每张贴纸是一整张图，不分部件。"""
    c = Ctx(a.ep)
    out = cmd_parse(a, quiet=True)
    H = c.show['hosts']; sd = c.sp(c.show['stickers_dir'])
    have = {k: {os.path.basename(f)[len(h['sticker_prefix']) + 1:-4] for f in glob.glob(os.path.join(sd, h['sticker_prefix'] + '_*.png'))} for k, h in H.items()}
    need = {k: {} for k in H}          # host -> label -> [line numbers]
    def want(who, label, i):
        need[who].setdefault(label, []).append(i)
    for r in out:
        who = r['who']; oth = 'B' if who == 'A' else 'A'
        dirs = ' '.join(d for _, d in r['dirs'])
        for t in r['tags']:
            if t['key'] == '贴纸' and t['val']: want(who, t['val'], r['i'])
            if t['key'] == '反应' and t['val']: want(oth, t['val'], r['i'])
        if not any(t['key'] == '贴纸' and t['start'] for t in r['tags']):
            for kw, label in H[who].get('direction_words', {}).items():
                if kw in dirs: want(who, label, r['i']); break
    lines = ['# 贴纸需求清单', '', f'稿子：{c.ep.get("script", "稿子.md")}。每张贴纸都是**一整张完整的角色图**（这个表情 + 这个动作），不分部件、不拼装，也不需要张嘴/眨眼版。', '']
    missing_total = 0
    for k, h in H.items():
        emo = h.get('emotions', {})
        rows, miss = [], []
        base = [('默认', h.get('default')), ('转场用', h.get('eyecatch')), ('封面用', h.get('cover_sticker'))]
        for label, sid in base:
            if sid and sid not in have[k]: miss.append((label, [], f'show.json 指定了 {sid}，但文件不在'))
        for label, ids in sorted(need[k].items(), key=lambda kv: kv[1][0]):
            sid = label if label in have[k] else emo.get(label)
            ok = bool(sid) and sid in have[k]
            rows.append(f"| {label} | {sid or '—'} | {'、'.join(f'第{i}句' for i in ids[:6])}{'…' if len(ids) > 6 else ''} | {'✅ 已有' if ok else '❗ 要画'} |")
            if not ok: miss.append((label, ids, '表情表里没有这个名字' if not sid else f'表情表指向 {sid}，但文件不在'))
        missing_total += len(miss)
        lines += [f"## {h['name']}（文件前缀 {h['sticker_prefix']}_）", '', '| 表情/动作 | 贴纸编号 | 用在 | 状态 |', '|---|---|---|---|'] + (rows or ['| （稿子里没指定，用默认） | | | |']) + ['']
        if miss:
            lines += [f"### 要给 {h['name']} 新画的贴纸", '']
            nxt = max([int(x.split('_')[0]) for x in have[k] if x.split('_')[0].isdigit()] + [0]) + 1
            for n, (label, ids, why) in enumerate(miss):
                ctx = [r for r in out if r['i'] in ids][:2]
                eg = '；'.join(f"第{r['i']}句「{r['text'][:30]}」" + (f"（{'、'.join(d for _, d in r['dirs'])}）" if r['dirs'] else '') for r in ctx)
                lines.append(f"- **{label}** → 建议文件名 `{h['sticker_prefix']}_{nxt + n:02d}_<英文名>.png`（{why}）" + (f"\n  - 用在：{eg}" if eg else ''))
            lines += ['', '画好后放进节目包的贴纸文件夹，并在 show.json 的 `hosts.' + k + '.emotions` 里加一行 `"表情名": "编号_英文名"`。', '']
    lines += ['## 每张贴纸的统一要求', '',
              '- 一张图 = 一个完整的角色（同一个人、同样的取景和大小），只换表情和动作；不分部件、不拼装。',
              '- 透明底 PNG（白底/纯绿底也行，会自动抠），建议正方形 1000 像素以上，角色在画面下部居中，四周留一点空。',
              '- 画风、描边、比例和现有贴纸一致（用同一个生图模型和参考图最稳）。',
              '- 身体位置不用和别的贴纸对齐，程序会按脚底自动摆放。',
              '- 不需要张嘴版、眨眼版：说话靠整张图的弹性拉伸表现。']
    dst = c.p('贴纸需求.md')
    open(dst, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(f'贴纸需求 -> {dst}：' + ('现有贴纸够用' if not missing_total else f'要新画 {missing_total} 张'))


# ------------------------------------------------------------------ dub scripts
def cmd_dub(a):
    c = Ctx(a.ep)
    out = cmd_parse(a, quiet=True)
    w = load_json(os.path.join(c.work, 'script.json')).get('warnings', [])
    if w:
        print('⚠ 稿子还有问题（配音稿照样生成，但建议先修好再给用户配音）：'); [print('  ⚠', x) for x in w]
    d = c.p('配音稿')
    os.makedirs(d, exist_ok=True)
    for k, h in c.show['hosts'].items():
        L = [r['spoken'] for r in out if r['who'] == k and not r.get('silent')]
        L = [re.sub(r'[「」『』《》“”"]', lambda m: '《' if m.group(0) == '《' else ('》' if m.group(0) == '》' else ''), x) for x in L]
        with open(os.path.join(d, f"{h['name']}_配音稿.txt"), 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(L) + '\n')
        print(f"{h['name']}: {len(L)} 句, {sum(len(x) for x in L)} 字 -> 配音稿/{h['name']}_配音稿.txt")
    order = [f"| {i+1} | {c.show['hosts'][r['who']]['name']} | {r['spoken']} |" for i, r in enumerate(out) if not r.get('silent')]
    with open(os.path.join(d, '对话顺序对照.md'), 'w', encoding='utf-8') as f:
        f.write('| 顺序 | 谁 | 台词 |\n|---|---|---|\n' + '\n'.join(order) + '\n')
    print('配音时：保持段落顺序，段与段之间留停顿；最好导出带时间码的字幕（srt）。')


# ------------------------------------------------------------------ audio io
def read_audio(path):
    import numpy as np
    if not os.path.exists(path):
        raise SystemExit(f'找不到音频文件：{path}（检查 episode.json 里的路径）')
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix='.wav'); os.close(fd)
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', path, '-ac', '1', '-ar', str(SR), tmp])
    w = wave.open(tmp)
    x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float32) / 32768
    w.close(); os.remove(tmp)
    return x


def write_wav(path, x):
    import numpy as np
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes()); w.close()


def parse_srt(p):
    txt = open(p, encoding='utf-8-sig').read().replace('\r', '')
    out = []
    for b in re.split(r'\n\s*\n', txt.strip()):
        L = b.strip().split('\n')
        for k, l in enumerate(L):
            m = re.match(r'(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)', l)
            if m:
                g = list(map(int, m.groups()))
                out.append({'a': g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, 'b': g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000,
                            'text': ''.join(L[k + 1:])})
                break
    return out


def voiced_runs(x, merge=0.12):
    import numpy as np
    hop = SR // 100; n = len(x) // hop
    e = np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1))
    thr = max(0.006, float(np.percentile(e, 95)) * 0.05)
    act = e > thr
    runs, s = [], None
    for i, v in enumerate(act):
        if v and s is None: s = i
        if not v and s is not None: runs.append([s / 100, i / 100]); s = None
    if s is not None: runs.append([s / 100, n / 100])
    m = []
    for r in runs:
        if m and r[0] - m[-1][1] < merge: m[-1][1] = r[1]
        else: m.append(r)
    return [r for r in m if r[1] - r[0] >= 0.04]


# ------------------------------------------------------------------ align
def align_host(x, srt, lines):
    """Map each script line (in this host's order) to [start,end] in the voice file + char->time map."""
    import numpy as np
    runs = voiced_runs(x)
    res = []
    if srt:
        stream, times, cidx = [], [], []
        for ci, ck in enumerate(srt):
            t = norm(ck['text'])
            n = max(1, len(t))
            for j, chh in enumerate(t):
                stream.append(chh); times.append(ck['a'] + (ck['b'] - ck['a']) * j / n); cidx.append(ci)
        stream = ''.join(stream); times.append(srt[-1]['b'] if srt else 0); cidx.append(len(srt) - 1)
        cur = 0
        for L in lines:
            tgt = norm(L['text'])
            if not tgt:
                res.append(None); continue
            win = stream[cur:cur + len(tgt) * 3 + 80]
            sm = difflib.SequenceMatcher(None, win, tgt, autojunk=False)
            blocks = [b for b in sm.get_matching_blocks() if b.size]
            if not blocks or sum(b.size for b in blocks) < 0.6 * len(tgt):
                # the script may skip a long stretch of the recording: look further ahead for the best-matching spot
                best = None
                for st in range(cur, max(cur + 1, len(stream) - len(tgt) // 2), max(1, len(tgt) // 3)):
                    w2 = stream[st:st + len(tgt) * 2 + 20]
                    sc = sum(b.size for b in difflib.SequenceMatcher(None, w2, tgt, autojunk=False).get_matching_blocks())
                    if best is None or sc > best[0]: best = (sc, st)
                if best and best[0] >= 0.6 * len(tgt):
                    cur2 = max(cur, best[1] - 10); win = stream[cur2:cur2 + len(tgt) * 3 + 80]
                    sm = difflib.SequenceMatcher(None, win, tgt, autojunk=False); blocks = [b for b in sm.get_matching_blocks() if b.size]
                    cur = cur2
                if not blocks or sum(b.size for b in blocks) < 0.6 * len(tgt):
                    res.append({'fail': True}); continue
            # map every target index -> stream index
            mp = [None] * len(tgt)
            for b in blocks:
                for q in range(b.size):
                    mp[b.b + q] = cur + b.a + q
            known = [(j, v) for j, v in enumerate(mp) if v is not None]
            for j in range(len(tgt)):
                if mp[j] is None:
                    prev = max([kv for kv in known if kv[0] < j], default=None, key=lambda kv: kv[0])
                    nxt = min([kv for kv in known if kv[0] > j], default=None, key=lambda kv: kv[0])
                    mp[j] = (prev[1] + (j - prev[0])) if prev else (nxt[1] - (nxt[0] - j))
            mp = [min(max(v, 0), len(stream) - 1) for v in mp]
            ctime = [times[v] for v in mp]
            first, last = mp[0], mp[-1]
            fi, li = cidx[first], cidx[last]
            ts = times[first]
            # end = end of the subtitle chunk holding the last char (or the next char's time if the line stops mid-chunk)
            te = srt[li]['b'] if last + 1 >= len(cidx) - 1 or cidx[last + 1] != li else times[last + 1]
            # hard limits: never reach into neighbouring subtitle chunks (lines cut from the script live there)
            starts_chunk = first == 0 or cidx[first - 1] != fi
            ends_chunk = cidx[last + 1] != li or last + 1 >= len(cidx) - 1
            lo = (srt[fi - 1]['b'] + 0.03 if fi > 0 else 0) if starts_chunk else ts
            hi = (srt[li + 1]['a'] - 0.03 if li + 1 < len(srt) else 1e9) if ends_chunk else te
            span = last - first + 1
            warn = span > len(tgt) * 1.35 + 3
            res.append({'ts': ts, 'te': te, 'lo': lo, 'hi': hi, 'ctime': ctime, 'warn_mid': warn})
            cur = last + 1
    else:
        # no subtitles: split by pauses into exactly len(lines) pieces
        segs = [r[:] for r in voiced_runs(x, merge=0.45)]
        need = sum(1 for L in lines if norm(L['text']))
        while len(segs) > need and len(segs) > 1:
            gaps = [segs[i + 1][0] - segs[i][1] for i in range(len(segs) - 1)]
            k = gaps.index(min(gaps)); segs[k][1] = segs[k + 1][1]; del segs[k + 1]
        it = iter(segs)
        for L in lines:
            tgt = norm(L['text'])
            if not tgt:
                res.append(None); continue
            s = next(it, None)
            if s is None:
                res.append({'fail': True}); continue
            n = len(tgt)
            res.append({'ts': s[0], 'te': s[1], 'lo': s[0] - 0.4, 'hi': s[1] + 0.4, 'ctime': [s[0] + (s[1] - s[0]) * j / n for j in range(n)], 'warn_mid': False})
    # refine with real voice activity
    def run_at(t):
        for r in runs:
            if r[0] - 0.02 <= t <= r[1] + 0.02: return r
        return None
    for k, r in enumerate(res):
        if not r or r.get('fail'): continue
        pe = next((res[q]['te'] for q in range(k - 1, -1, -1) if res[q] and not res[q].get('fail')), 0)
        ns = next((res[q]['ts'] for q in range(k + 1, len(res)) if res[q] and not res[q].get('fail')), len(x) / SR)
        ts, te = r['ts'], r['te']
        rr = run_at(ts) or next((q for q in runs if q[0] >= ts - 0.05), None)
        s0 = ts
        if rr and ts - rr[0] < 0.35: s0 = min(ts, rr[0])
        # stutter / breath just before (separated from previous line) belongs to this line
        for q in runs:
            if pe + 0.25 <= q[0] < s0 and q[0] >= r.get('lo', 0) and s0 - q[1] < 0.6: s0 = q[0]; break
        s0 = max(s0, pe + 0.03, r.get('lo', 0))
        re_ = run_at(te - 0.02)
        e0 = te
        hi = r.get('hi', 1e9)
        if re_ and re_[1] - te < (0.8 if hi > te else 0.35): e0 = max(te, re_[1])   # subtitle ended early: keep the tail
        e0 = min(e0, ns - 0.03, max(te, r.get('hi', 1e9)))
        r['s0'], r['e0'] = max(0, s0), max(s0 + 0.1, e0)
    return res


def cmd_align(a):
    import numpy as np
    c = Ctx(a.ep)
    lines = cmd_parse(a, quiet=True)
    V = c.ep['voice']
    info, src = {}, {}
    for k in ['A', 'B']:
        x = read_audio(c.p(V[k]['audio']))
        srt = parse_srt(c.p(V[k]['srt'])) if V[k].get('srt') and os.path.exists(c.p(V[k]['srt'])) else None
        mine = [L for L in lines if L['who'] == k and not L.get('silent')]
        res = align_host(x, srt, mine)
        for L, r in zip(mine, res):
            info[L['i']] = r
        src[k] = x
        print(f"{c.show['hosts'][k]['name']}: {len(mine)} 句，{'用配音字幕对齐' if srt else '无字幕，只按停顿切分（请人工抽查）'}")
    bad = [i for i, r in info.items() if not r or r.get('fail')]
    for i in bad:
        print(f'✘ 第{i}句 在配音里找不到对应的话（是不是稿子改过但没重配？）')
    for i, r in info.items():
        if r and r.get('warn_mid'):
            print(f'⚠ 第{i}句 稿子可能删了句子中间的字，配音里多出的部分会被一起保留')
    if bad and not a.force:
        raise SystemExit('对齐失败，修正后重跑（或 --force 跳过这些句子）')
    # ---- timeline
    T = c.show.get('timing', {})
    G = {'switch': T.get('gap_switch', 0.36), 'same': T.get('gap_same', 0.42), 'interrupt': T.get('gap_interrupt', 0.14),
         'section': T.get('gap_section', 1.45), 'clip': T.get('gap_into_clip', 0.5), 'start': T.get('start', 2.8), 'tail': T.get('tail', 2.4),
         'hook_start': T.get('hook_start', 0.8), 'after_hook': T.get('gap_after_hook', 3.3)}
    t = G['hook_start'] if lines and lines[0].get('hook') else G['start']; prev = None; out = []
    for L in lines:
        r = info.get(L['i'])
        pre = 0.0
        for tg in L['tags']:
            if tg['key'] == '独奏':
                try: pre = float(tg['val'] or 2.5)
                except ValueError: pre = 2.5
        if prev is not None:
            g = G['same'] if prev['who'] == L['who'] else G['switch']
            if prev['text'].rstrip().endswith(('——', '—')): g = G['interrupt']
            if L['sec']: g = G['section']
            if L['clip'] and L['clip'].get('segs') and not (prev.get('clip') and prev['clip'].get('segs')): g = max(g, G['clip'])
            if L.get('hook') and prev.get('hook'): g = G['same'] if prev['who'] == L['who'] else G['switch']   # 看点速报 keeps a fast pace
            if prev.get('hook') and not L.get('hook'): g = G['after_hook']                                      # room for the title sting
            t = prev['t1'] + g + pre
        if L.get('silent') or not r or r.get('fail'):
            rec = dict(L, t0=round(t, 3), t1=round(t + 1.8, 3), src=None, ctime=[], silent=True)
        else:
            s0, e0 = r['s0'], r['e0']
            rec = dict(L, t0=round(t, 3), t1=round(t + (e0 - s0), 3), src=[max(0, s0 - 0.05), e0 + 0.06], src0=s0,
                       ctime=[round(t + (ct - s0), 3) for ct in r['ctime']])
        rec['pre'] = pre
        out.append(rec); prev = rec
    END = round(prev['t1'] + G['tail'], 2)
    n = int(END * SR) + SR
    tr = {'A': np.zeros(n, np.float32), 'B': np.zeros(n, np.float32)}
    for r in out:
        if not r.get('src'): continue
        s = src[r['who']][int(r['src'][0] * SR):int(r['src'][1] * SR)].copy()
        f = int(.012 * SR); s[:f] *= np.linspace(0, 1, f); f2 = int(.04 * SR); s[-f2:] *= np.linspace(1, 0, f2)
        i0 = int((r['t0'] - (r['src0'] - r['src'][0])) * SR)
        tr[r['who']][i0:i0 + len(s)] += s
    hop = SR // 100; m = n // hop
    ea = np.sqrt((tr['A'][:m * hop].reshape(m, hop) ** 2).mean(1)); eb = np.sqrt((tr['B'][:m * hop].reshape(m, hop) ** 2).mean(1))
    ov = int(((ea > 0.01) & (eb > 0.01)).sum())
    np.save(os.path.join(c.work, 'voice_A.npy'), tr['A'][:int(END * SR)]); np.save(os.path.join(c.work, 'voice_B.npy'), tr['B'][:int(END * SR)])
    save_json(os.path.join(c.work, 'timeline.json'), {'end': END, 'lines': out, 'overlap_10ms': ov})
    print(f'时间线 {END:.1f} 秒，{len(out)} 句；两人声音重叠 {ov*10} 毫秒' + ('（正常应为 0）' if ov else ''))


# ------------------------------------------------------------------ stage (auto storyboard)
def cmd_stage(a):
    c = Ctx(a.ep)
    tl = load_json(os.path.join(c.work, 'timeline.json'))
    L = tl['lines']; END = tl['end']
    H = c.show['hosts']
    stickers = {k: sorted({os.path.basename(f)[len(h['sticker_prefix']) + 1:-4] for f in glob.glob(os.path.join(c.sp(c.show['stickers_dir']), h['sticker_prefix'] + '_*.png'))
                           if '_talk' not in f and '_blink' not in f}) for k, h in H.items()}
    # 表情表里登记过、但还没画的贴纸也算数：渲染时用占位小人，qa 会列出来
    for k, h in H.items():
        declared = set(h.get('emotions', {}).values()) | {h.get(x) for x in ('default', 'eyecatch', 'cover_sticker') if h.get(x)}
        missing = sorted(declared - set(stickers[k]))
        stickers[k] = sorted(set(stickers[k]) | declared)
        if missing: print(f"  {h['name']} 有 {len(missing)} 张贴纸还没画，渲染时用占位小人")
        if not stickers[k]: raise SystemExit(f"{h['name']} 没有贴纸，show.json 里也没有表情表（hosts.{k}.emotions）")

    def emo(who, label):
        if not label: return None
        if label in stickers[who]: return label
        sid = H[who].get('emotions', {}).get(label)
        return sid if sid in stickers[who] else None

    def auto_emo(who, text_dirs):
        for kw, label in H[who].get('direction_words', {}).items():
            if kw in text_dirs:
                return emo(who, label)
        return None

    def t_at(r, off):
        """time of character offset `off` (in display text) inside line r"""
        if not r['ctime']: return r['t0']
        sp = norm(r['text'][:off])
        j = min(len(sp), len(r['ctime']) - 1)
        return r['ctime'][j] if r['ctime'] else r['t0']

    def anchor_t(r, anchor):
        if not anchor: return None
        k = r['text'].find(anchor)
        if k < 0:
            k2 = norm(r['text']).find(norm(anchor))
            if k2 < 0: return None
            return r['ctime'][min(k2, len(r['ctime']) - 1)] - 0.05
        return t_at(r, k) - 0.05

    pal = ['gold', 'pink', 'blue', 'mint', 'purple', 'red']
    out = []; pi = 0
    for idx, r in enumerate(L):
        who = r['who']; oth = 'B' if who == 'A' else 'A'
        R = {'i': r['i'], 'who': who, 'text': r['text'], 't0': r['t0'], 't1': r['t1'], 'sec': r.get('sec'), 'pre': r.get('pre', 0)}
        # subtitle phrases from the spoken text, timed by the char map
        ch = []
        if r['ctime']:
            sp = r['spoken']; pos = 0
            for ph in phrases(sp, c.show.get('ui', {}).get('subtitle_max_chars', 22)):
                n0 = len(norm(sp[:sp.find(ph, pos)])) if sp.find(ph, pos) >= 0 else pos
                n1 = n0 + len(norm(ph))
                pos = sp.find(ph, pos) + len(ph) if sp.find(ph, pos) >= 0 else pos
                a0 = r['ctime'][min(n0, len(r['ctime']) - 1)]
                a1 = r['ctime'][min(max(n1 - 1, 0), len(r['ctime']) - 1)] + 0.15
                ch.append({'t0': round(max(r['t0'], a0), 3), 't1': round(min(r['t1'], a1), 3), 'text': ph})
        R['chunks'] = ch
        tags = r['tags']
        dirs_txt = ' '.join(d for _, d in r['dirs'])
        st = None; R['atT'] = []; R['fxT'] = []; R['kwT'] = []; R['fx'] = []
        for tg in tags:
            kkey, v = tg['key'], tg['val']
            if kkey == '贴纸':
                sid = emo(who, v)
                if tg['start'] or st is None and tg['off'] < 2:
                    st = sid or st
                elif sid:
                    R['atT'].append([round(t_at(r, tg['off']) - 0.05, 3), who, sid])
            elif kkey == '反应':
                sid = emo(oth, v)
                if sid: R['re'] = sid
            elif kkey == '镜头':
                cv = CAM.get(v) or (c.host_of(v[2:]) if v.startswith('特写') else None) or 'wide'; R['cam'] = who if cv == 'SPK' else cv
            elif kkey == '特效':
                for f in [x for x in re.split(r'[、,，+ ]+', v) if x]:
                    if f in FX:
                        if tg['start']: R['fx'].append(FX[f])
                        else: R['fxT'].append([round(t_at(r, tg['off']) - 0.05, 3), FX[f]])
            elif kkey == '要点':
                txt, _, col = v.partition('|')
                txt, _, anc = txt.partition('@')
                at = anchor_t(r, anc.strip()) if anc else None
                if at is None and r.get('hook'):
                    at = r['t0'] + 0.25            # 看点速报: the keyword lands together with the line
                if at is None:
                    at = anchor_t(r, txt.strip()) if txt.strip() and r['text'].find(txt.strip()) >= 0 else (t_at(r, tg['off']) if not tg['start'] else r['t0'] + 0.1)
                R['kwT'].append([round(at + 0.05, 3), txt.strip(), col.strip() or pal[pi % len(pal)]]); pi += 1
            elif kkey in ('天气', '信息牌'):
                R['badge'] = v
            elif kkey == '收屏':
                R['closeT'] = round((anchor_t(r, v) or r['t0']) - 0.07, 3)
        # emotion from stage directions if no explicit sticker
        if not st:
            st = auto_emo(who, dirs_txt)
        clipd = r.get('clip') or {}
        if not st:
            st = emo(who, '讲解') if clipd.get('segs') else None
        R['st'] = st or H[who].get('default', stickers[who][0])
        if r.get('silent'):
            R['chunks'] = []
        if r.get('hook'):
            R['hook'] = True; R.pop('cam', None)
            bub = next((tg['val'] for tg in tags if tg['key'] == '气泡'), None)
            if bub is None:
                m = re.match(r'^(什么|竟然|等等|还有|哇|诶|欸|天哪|不是吧)[^，。！？!?]{0,4}[！？!?]+', r['text'])
                bub = m.group(0) if m else ('？！' if re.search(r'[？?][！!]|[！!][？?]', r['text']) else '')
            R['bubble'] = bub
            R['_outro'] = any(tg['key'] == '收尾' for tg in tags) or bool(re.search(r'继续(观看|往下看|看下去)|往下看', r['text']))
        # camera default rules
        if 'cam' not in R and not clipd.get('segs') and not r.get('hook'):
            prv = L[idx - 1] if idx else None; nxt = L[idx + 1] if idx + 1 < len(L) else None
            short = len(r['text']) <= 14
            banter = prv and nxt and prv['who'] != who and nxt['who'] != who and short
            if r.get('sec') or banter or (prv and prv['who'] != who and short):
                R['cam'] = 'wide'
            elif '！' in r['text'] or '!' in r['text']:
                R['cam'] = who
            else:
                R['cam'] = 'wide'
        if 'closeT' in R and 'cam' in R:
            R['camAfter'] = R['cam']
        R['clip'] = clipd
        out.append(R)
    # ---- 看点速报 (cold open): item numbering, frame mode, where the title sting goes
    hook_lines = [r for r in out if r.get('hook')]
    hook_end = round(max(r['t1'] for r in hook_lines) + 0.35, 3) if hook_lines else None
    outro = False; n = 0
    for r in hook_lines:
        outro = outro or r.pop('_outro', False)
        if outro: r['hookMode'] = 'outro'
        else:
            n += 1; r['hookN'] = n; r['hookMode'] = 'clip' if r['clip'].get('segs') or r['clip'].get('keep') else 'mystery'
    for r in out: r.pop('_outro', None)
    # ---- clip windows
    wins = []; cur = None
    for r, src in zip(out, L):
        clipd = r['clip']; t0 = r['t0'] - 0.12 - r.get('pre', 0)
        if cur and cur.get('hook') and not r.get('hook'):
            cur['close'] = hook_end; cur = None          # never let a 看点速报 window run into the studio
        if clipd.get('segs'):
            if not cur:
                cur = {'open': round(t0, 3), 'segs': [], 'hook': bool(r.get('hook'))}; wins.append(cur)
            for k2, sg in enumerate(clipd['segs']):
                at = t0 if k2 == 0 else (anchor_t(src, sg['anchor']) if sg.get('anchor') else None)
                if at is None: at = t0 if k2 == 0 else r['t0'] + (r['t1'] - r['t0']) * k2 / len(clipd['segs'])
                cur['segs'].append({'t': round(at, 3), 'a': sg['src'], 'orig': sg['orig'], 'note': sg.get('note', '')})
        elif not clipd.get('keep') and cur:
            cur['close'] = round(r['t0'] - 0.12, 3); cur = None
        if r.get('closeT') is not None and cur:
            cur['close'] = r['closeT']; cur = None
    if cur: cur['close'] = END
    if wins and out and out[0].get('hook') and wins[0].get('hook'): wins[0]['open'] = 0.0   # footage is already in the frame when the show starts
    cp = os.path.join(c.work, 'clipcrop.json'); crops = load_json(cp) if os.path.exists(cp) else {}
    fill_lb = c.show.get('footage', {}).get('fill_letterbox', True)
    for wi, w in enumerate(wins):
        for si, s in enumerate(w['segs']):
            en = w['segs'][si + 1]['t'] if si + 1 < len(w['segs']) else w['close'] + 0.3
            s['dur'] = round(en - s['t'], 3); s['id'] = f'w{wi:02d}s{si}'
            d = os.path.join(c.work, 'site', 'clipf', s['id'])
            if os.path.isdir(d) and os.listdir(d):
                s['dir'] = f"clipf/{s['id']}"; s['n'] = len(os.listdir(d))
            cr = crops.get(s['id'])
            if cr and fill_lb and '保留黑边' not in s.get('note', '') and (cr[3] < 720 * 0.96 or cr[2] < 1280 * 0.96):
                s['crop'] = cr
    for r in out:
        r.pop('clip', None)
    env = {}
    import numpy as np
    for k in 'AB':
        x = np.load(os.path.join(c.work, f'voice_{k}.npy')); hop = SR // 60; m = len(x) // hop
        e = np.sqrt((x[:m * hop].reshape(m, hop) ** 2).mean(1)); s = np.sort(e[e > 1e-4]); p95 = s[int(len(s) * .95)] if len(s) else 1
        env[k] = [round(float(v), 3) for v in np.clip(e / (p95 + 1e-6), 0, 1)]
    show_pub = {'hosts': {k: {kk: vv for kk, vv in h.items() if kk not in ('card',)} for k, h in H.items()},
                'channel': c.show.get('channel', {}), 'show_name': c.show.get('show_name', ''), 'studio': c.show.get('studio', {}),
                'animation': c.show.get('animation', {}), 'effects': c.show.get('effects', {}), 'ui': c.show.get('ui', {}), 'scene': c.show.get('scene', {})}
    ep_pub = {'sting_sub': c.ep.get('sting_sub', ''), 'ticker': c.ep.get('ticker', []), 'date': c.ep.get('date', '2026-01-01 20:00'),
              'section0': c.ep.get('section0', ''), 'hook_end': hook_end, 'sting_t': hook_end or 0, 'hook_total': n,
              'hook_title': c.show.get('ui', {}).get('hook_title', '看点速报')}
    film = {'end': END, 'lines': out, 'wins': wins, 'env': env, 'stk': stickers, 'show': show_pub, 'ep': ep_pub}
    save_json(os.path.join(c.work, 'film.json'), film)
    print(f"分镜完成：{len(out)} 句，大屏片段 {sum(len(w['segs']) for w in wins)} 段（{len(wins)} 次推进大屏），要点贴纸 {sum(len(r['kwT']) for r in out)} 个")


# ------------------------------------------------------------------ clips
def fmt_t(s):
    s = int(round(s)); return f'{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}'


def cmd_clips(a):
    c = Ctx(a.ep)
    film = load_json(os.path.join(c.work, 'film.json'))
    rows = [(s['id'], s['a'], int(math.ceil(s['dur'] + 2.5)), s['orig'], s.get('note', '')) for w in film['wins'] for s in w['segs']]
    src = c.ep.get('source_video', '')
    out_dir = c.ep.get('clips_dir', '片段')
    vf = 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2'
    if a.cut:
        os.makedirs(c.p(out_dir), exist_ok=True)
        for cid, st, du, o, _ in rows:
            sh(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-ss', str(st), '-i', c.p(src), '-t', str(du), '-vf', vf,
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', os.path.join(c.p(out_dir), cid + '.mp4')])
            print('done', cid)
        return
    ps = ['$src = "' + (c.ep.get('source_video_win') or src) + '"', '$out = "' + (c.ep.get('clips_dir_win') or out_dir) + '"',
          'New-Item -ItemType Directory -Force -Path $out | Out-Null', '$clips = @(']
    ps.append(',\n'.join(f' @("{cid}","{fmt_t(st)}",{du})' for cid, st, du, _, _ in rows))
    ps += [')', 'foreach ($c in $clips) {',
           f'  ffmpeg -y -hide_banner -loglevel error -ss $c[1] -i $src -t $c[2] -vf "{vf}" -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -c:a aac -b:a 160k "$out\\$($c[0]).mp4"',
           '  Write-Host "done $($c[0])"', '}']
    shl = [f'SRC="{src}"', f'OUT="{out_dir}"', 'mkdir -p "$OUT"']
    for cid, st, du, _, _ in rows:
        shl.append(f'ffmpeg -y -hide_banner -loglevel error -ss {st} -i "$SRC" -t {du} -vf "{vf}" -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -c:a aac -b:a 160k "$OUT/{cid}.mp4"')
    open(os.path.join(c.ep_dir, '截片段.ps1'), 'w', encoding='utf-8-sig').write('\n'.join(ps) + '\n')
    open(os.path.join(c.ep_dir, '截片段.sh'), 'w', encoding='utf-8').write('\n'.join(shl) + '\n')
    tbl = ['| 文件 | 开始 | 时长 | 成片用原声 | 说明 |', '|---|---|---|---|---|'] + [f'| {cid} | {fmt_t(st)[3:]} | {du} 秒 | {"✅" if o else "—"} | {n} |' for cid, st, du, o, n in rows]
    open(os.path.join(c.ep_dir, '截片段清单.md'), 'w', encoding='utf-8').write('\n'.join(tbl) + '\n')
    print(f'{len(rows)} 段片段。已生成 截片段.ps1（Windows PowerShell，UTF-8 BOM）、截片段.sh（Linux/mac）、截片段清单.md。')
    print(f'截好的文件放进本期文件夹的「{out_dir}」，文件名保持 w00s0.mp4 这样。')


def cmd_bsub(a):
    """B 站字幕 JSON（接口原样、body 数组，或 [[from,to,text],...]，可以是几个分段文件）-> 原视频字幕.srt"""
    c = Ctx(a.ep)
    items = []
    for f in a.inp.split(','):
        d = load_json(f)
        if isinstance(d, dict): d = d.get('body') or d.get('data', {}).get('body') or []
        for x in d:
            items.append((x['from'], x['to'], x['content']) if isinstance(x, dict) else tuple(x[:3]))
    items = sorted(set(items))
    def ft(t):
        ms = int(round(t * 1000)); return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'
    out = c.p(c.ep.get('source_srt', '原视频字幕.srt'))
    with open(out, 'w', encoding='utf-8') as fh:
        for k, (a0, b0, tx) in enumerate(items, 1):
            fh.write(f'{k}\n{ft(a0)} --> {ft(b0)}\n{tx}\n\n')
    print(f'{len(items)} 条字幕 -> {out}')


def cmd_speechmap(a):
    c = Ctx(a.ep)
    srt = parse_srt(c.p(c.ep['source_srt']))
    print('原视频里连续 ≥3 秒没有官方讲解的时间段（适合留原声）：')
    for i in range(len(srt) - 1):
        g0, g1 = srt[i]['b'], srt[i + 1]['a']
        if g1 - g0 >= 3:
            print(f"  {fmt_t(g0)[3:]}–{fmt_t(g1)[3:]}  {g1-g0:4.0f}秒  前:{srt[i]['text'][:16]}  后:{srt[i+1]['text'][:16]}")
    fp = os.path.join(c.work, 'film.json')
    if os.path.exists(fp):
        film = load_json(fp)
        print('\n标了「原声」的片段，官方讲解覆盖率（>30% 建议换时间段或去掉原声）：')
        for w in film['wins']:
            for s in w['segs']:
                if not s['orig']: continue
                a0, b0 = s['a'], s['a'] + s['dur']
                cov = sum(max(0, min(b0, q['b']) - max(a0, q['a'])) for q in srt) / max(0.1, s['dur'])
                print(f"  {s['id']} {fmt_t(a0)[3:]} 讲解覆盖 {cov*100:3.0f}% {'⚠' if cov > 0.3 else '✔'}")


def cmd_prepclips(a):
    c = Ctx(a.ep)
    film = load_json(os.path.join(c.work, 'film.json'))
    cd = c.p(c.ep.get('clips_dir', '片段'))
    miss = []; crops = {}
    for w in film['wins']:
        for s in w['segs']:
            f = os.path.join(cd, s['id'] + '.mp4')
            if not os.path.exists(f):
                miss.append(s['id']); continue
            d = os.path.join(c.work, 'site', 'clipf', s['id']); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
            sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', f, '-vf', 'fps=30,scale=1280:720', '-q:v', '3', os.path.join(d, '%05d.jpg')])
            # letterbox: area that is black in EVERY frame (cropdetect with reset=0 keeps the union of picture)
            r = subprocess.run(['ffmpeg', '-hide_banner', '-i', f, '-vf', 'cropdetect=limit=24:round=2:reset=0', '-f', 'null', '-'],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            m = re.findall(r'crop=(\d+):(\d+):(\d+):(\d+)', r.stderr)
            if m:
                cw, ch_, cx, cy = map(int, m[-1]); crops[s['id']] = [cx, cy, cw, ch_]
            os.makedirs(os.path.join(c.work, 'clipa'), exist_ok=True)
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f, '-vn', '-ac', '1', '-ar', str(SR), os.path.join(c.work, 'clipa', s['id'] + '.wav')])
            print(s['id'], len(os.listdir(d)), '帧')
    if miss:
        print('⚠ 缺少片段:', ' '.join(miss), '（大屏会显示黑底，先运行 clips 生成截取命令）')
    save_json(os.path.join(c.work, 'clipcrop.json'), crops)
    bars = [k for k, v in crops.items() if v[3] < 720 * 0.96 or v[2] < 1280 * 0.96]
    if bars: print('有黑边、会自动放大填满大屏的片段:', ' '.join(bars), '（不想裁就在稿子 🎬 说明里写「保留黑边」）')
    cmd_stage(a)  # refresh frame dirs in film.json


# ------------------------------------------------------------------ audio (sfx + original bed)
def cmd_audio(a):
    import numpy as np
    from sfxlib import make_sfx
    c = Ctx(a.ep)
    film = load_json(os.path.join(c.work, 'film.json'))
    L, W, END = film['lines'], film['wins'], film['end']
    n = int(END * SR)
    S = make_sfx(SR)
    H = c.show['hosts']
    def kind(who, sid):
        m = H[who].get('fxkind', {})
        if sid in m: return m[sid]
        for rx, kd in [('point|explain', 'point'), ('fist|raise|wave', 'up'), ('slam', 'slam'), ('surprised', 'surprise'), ('angry', 'angry'),
                       ('panic|shiver|teary', 'sweat'), ('smug|sparkle|laugh|happy|bow|icecream|count', 'sparkle')]:
            if re.search(rx, sid): return kd
        return 'soft'
    ev = []
    add = lambda t, nm, g=1.: ev.append((t, nm, g))
    st0 = film['ep'].get('sting_t') or 0
    add(st0, 'swoosh'); add(st0 + 0.12, 'hit')
    first_after_hook = next((r['i'] for r in L if not r.get('hook')), None) if any(r.get('hook') for r in L) else None
    cur = {'A': H['A'].get('default'), 'B': H['B'].get('default')}
    def setst(t, who, sid):
        if cur.get(who) != sid:
            add(t, 'pop')
            if kind(who, sid) not in ('soft', 'sweat'): add(t + .03, 'twinkle', .8)
        cur[who] = sid
    sec_t0 = {round(r['t0'] - 0.12 - r.get('pre', 0), 3) for r in L if r.get('sec')} | {round(r['t0'] - 0.12, 3) for r in L if r.get('sec')}
    for w in W:
        if w.get('hook'): continue
        inst_o = any(abs(w['open'] - s) < 0.02 for s in sec_t0); inst_c = any(abs(w['close'] - s) < 0.02 for s in sec_t0) or w['close'] >= END - 0.01
        if not inst_o: add(w['open'], 'whoosh'); add(w['open'] + .55, 'zap')
        if not inst_c: add(w['close'], 'zap'); add(w['close'] + .06, 'whoosh_out'); add(w['close'] + .64, 'pop', .7)
    for li, r in enumerate(L):
        who = r['who']; oth = 'B' if who == 'A' else 'A'; t0 = r['t0'] - 0.12
        if r.get('sec') and li > 0 and not r.get('hook') and r['i'] != first_after_hook: add(r['t0'] - 1.35, 'swoosh'); add(r['t0'] - 1.08, 'hit', .8); add(r['t0'] - 0.4, 'swoosh', .8)
        if r.get('hook'):
            add(t0, 'whoosh', .7); add(t0 + .1, 'hit', .9)
            if r.get('bubble'): add(t0 + .18, 'boing', .8)
        if li == 0 and r.get('hook'): add(0.0, 'swoosh')
        if r.get('st'): setst(t0, who, r['st'])
        if r.get('re'): setst(t0, oth, r['re'])
        if r.get('badge'): add(t0 + .1, 'ding')
        for f in r.get('fx', []):
            add(t0, {'slam': 'thump', 'exclaim': 'boing', 'question': 'boing', 'sparkle': 'twinkle', 'flash': 'zap'}.get(f, 'pop'), .8)
        for t, w2, s in r.get('atT', []): setst(t, w2, s)
        for t, f in r.get('fxT', []):
            add(t, {'slam': 'thump', 'sparkle': 'twinkle'}.get(f, 'pop'), .8)
        for t, tx, col in r.get('kwT', []): add(t, 'boing')
        if not r['chunks'] and r.get('st'): add(t0, 'hit'); add(t0 + .05, 'twinkle', 1.3)
    sfx = np.zeros(n, np.float32)
    for t, nm, g in sorted(ev):
        i = int(max(0, t) * SR); s = S[nm] * g; j = min(n, i + len(s)); sfx[i:j] += s[:j - i]
    voice = (np.load(os.path.join(c.work, 'voice_A.npy')) + np.load(os.path.join(c.work, 'voice_B.npy')))[:n]
    # ducking envelope from the hosts' voices
    hop = SR // 100; m = len(voice) // hop
    ve = np.sqrt((voice[:m * hop].reshape(m, hop) ** 2).mean(1)); act = (ve > 0.012).astype(np.float32)
    duck = np.zeros(m, np.float32); s_ = 0.
    for i in range(m):
        k = 0.45 if act[i] > s_ else 0.03; s_ += k * (act[i] - s_); duck[i] = s_
    duck = np.pad(np.repeat(duck, hop), (0, max(0, n - m * hop)))[:n]
    bed = np.zeros(n, np.float32)
    lvl0 = c.show.get('audio', {}).get('orig_level', 0.32)
    for w in W:
        inst = any(abs(w['open'] - s) < 0.02 for s in sec_t0); vis0 = w['open'] + (0 if inst else .55)
        for si, sg in enumerate(w['segs']):
            if not sg.get('orig'): continue
            f = os.path.join(c.work, 'clipa', sg['id'] + '.wav')
            if not os.path.exists(f): print('⚠ 缺少原声', sg['id']); continue
            wv = wave.open(f); x = np.frombuffer(wv.readframes(wv.getnframes()), '<i2').astype(np.float32) / 32768; wv.close()
            x = x * (0.12 / (np.sqrt((x ** 2).mean()) + 1e-6))
            t0 = sg['t']; t1 = w['segs'][si + 1]['t'] if si + 1 < len(w['segs']) else w['close']
            i0 = int(t0 * SR); i1 = min(n, int(t1 * SR)); seg = x[:i1 - i0]
            if len(seg) < i1 - i0: seg = np.pad(seg, (0, i1 - i0 - len(seg)))
            tt = np.arange(i1 - i0) / SR + t0
            g = np.clip((tt - vis0) / 0.3, 0, 1) * np.clip((w['close'] - tt) / 0.25, 0, 1)
            fi = int(.15 * SR)
            if si > 0: g[:fi] *= np.linspace(0, 1, fi)
            if si + 1 < len(w['segs']): g[-fi:] *= np.linspace(1, 0, fi)
            lvl = lvl0 * (1.7 if any(r.get('pre') and abs((r['t0'] - 0.12 - r['pre']) - t0) < 0.05 for r in L) else 1)
            bed[i0:i1] += seg * g * lvl * (1 - 0.62 * duck[i0:i1])
    mix = voice + np.tanh(sfx * 1.2) * c.show.get('audio', {}).get('sfx_level', 0.5) + np.tanh(bed / 0.6) * 0.6
    mix *= 0.95 / max(1e-6, np.abs(mix).max())
    write_wav(os.path.join(c.work, 'master.wav'), mix)
    print(f'混音完成：音效 {len(ev)} 处，原声 {sum(1 for w in W for s in w["segs"] if s.get("orig"))} 段 -> work/master.wav')


# ------------------------------------------------------------------ render
def copy_scene(show_dir, show, site):
    """Put the scene script at site/scene/scene.js and its files next to it."""
    t, script, adir = scene_paths(show_dir, show)
    sd = os.path.join(site, 'scene'); shutil.rmtree(sd, ignore_errors=True); os.makedirs(sd, exist_ok=True)
    if adir and os.path.isdir(adir):
        for f in glob.glob(os.path.join(adir, '**', '*'), recursive=True):
            if os.path.isfile(f):
                d = os.path.join(sd, os.path.relpath(f, adir)); os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy(f, d)
    if not os.path.exists(script): raise SystemExit(f'找不到场景脚本 {script}（检查 show.json → scene）')
    shutil.copy(script, os.path.join(sd, 'scene.js'))


def package_paths(show_dir, show):
    """The packaging script (台标/新闻栏/转场/片头/看点速报/灯光/特效): the show pack's own one if set, else the plain placeholder."""
    p = show.get('package')
    if p: return os.path.join(show_dir, p), os.path.dirname(os.path.join(show_dir, p))
    return os.path.join(KIT, 'engine', 'package.js'), None


def copy_engine(site, show_dir=None, show=None):
    shutil.copy(os.path.join(KIT, 'engine', 'studio.html'), os.path.join(site, 'film.html'))
    for f in ('core.js', 'film_ctrl.js'): shutil.copy(os.path.join(KIT, 'engine', f), os.path.join(site, f))
    script, adir = package_paths(show_dir, show or {}) if show_dir else (os.path.join(KIT, 'engine', 'package.js'), None)
    pd = os.path.join(site, 'pkg'); shutil.rmtree(pd, ignore_errors=True); os.makedirs(pd, exist_ok=True)
    if adir and os.path.isdir(adir):
        for f in glob.glob(os.path.join(adir, '**', '*'), recursive=True):
            if os.path.isfile(f):
                d = os.path.join(pd, os.path.relpath(f, adir)); os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy(f, d)
    if not os.path.exists(script): raise SystemExit(f'找不到包装脚本 {script}（检查 show.json → package）')
    shutil.copy(script, os.path.join(pd, 'package.js'))


def copy_brand(show_dir, show, site):
    asd = os.path.join(site, 'assets'); os.makedirs(asd, exist_ok=True)
    ch = show.get('channel', {})
    for key, name in [('station_logo', 'station.png'), ('title_art', 'title.png')]:
        src = os.path.join(show_dir, ch[key]) if ch.get(key) else None
        if src and os.path.exists(src): shutil.copy(src, os.path.join(asd, name))
        elif os.path.exists(os.path.join(asd, name)): os.remove(os.path.join(asd, name))


def prepare_site(c):
    site = os.path.join(c.work, 'site'); os.makedirs(site, exist_ok=True)
    copy_engine(site, c.show_dir, c.show); copy_scene(c.show_dir, c.show, site); copy_brand(c.show_dir, c.show, site)
    st = os.path.join(site, 'stk'); os.makedirs(st, exist_ok=True)
    for f in glob.glob(os.path.join(c.sp(c.show['stickers_dir']), '*.png')):
        dst = os.path.join(st, os.path.basename(f))
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(f): shutil.copy(f, dst)
    shutil.copy(os.path.join(c.work, 'film.json'), os.path.join(site, 'film.json'))
    return site


class Server:
    """Local static server for the render site. Picks a free port if the asked one is busy, waits until it answers."""
    def __init__(self, root, port):
        import socket, urllib.request
        def free(pt):
            with socket.socket() as so:
                try: so.bind(('127.0.0.1', pt)); return True
                except OSError: return False
        if not free(port):
            with socket.socket() as so: so.bind(('127.0.0.1', 0)); port = so.getsockname()[1]
        self.port = port
        self.p = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'], cwd=root,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try: urllib.request.urlopen(f'http://127.0.0.1:{port}/film.json', timeout=1).read(1); break
            except Exception: time.sleep(0.2)
        else:
            self.stop(); raise SystemExit('本地网页服务起不来（端口被占？换 --port 试试）')
    def stop(self):
        self.p.terminate()


def cjk_font(size):
    """A font that can draw Chinese labels on preview sheets (None if the system has none)."""
    from PIL import ImageFont
    cands = ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf', '/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Medium.ttc']
    if shutil.which('fc-list'):
        r = subprocess.run(['fc-list', ':lang=zh', 'file'], capture_output=True, text=True)
        fl = [x.split(':')[0].strip() for x in r.stdout.splitlines() if x.strip()]
        cands = sorted(fl, key=lambda f: (('Sans' not in f) + ('CJK' not in f and 'Hei' not in f), 'Bold' not in f)) + cands
    for f in cands:
        try:
            if f and os.path.exists(f): return ImageFont.truetype(f, size)
        except Exception: pass
    return None


def scene_film(show):
    """A tiny fake episode that walks the camera through the set: wide, both close-ups, push into the screen, dutch angle."""
    H = show['hosts']
    plan = [('A', 1.0, 4.0, 'wide', '全景：看两位主播站位、主播台、大屏'), ('A', 5.0, 8.0, 'A', '近景：主播 A'), ('B', 9.0, 12.0, 'B', '近景：主播 B'),
            ('B', 13.0, 18.0, None, '推进大屏：实机画面铺满'), ('A', 19.0, 22.0, 'dutch', '倾斜镜头'), ('B', 23.0, 26.0, 'wide', '回到全景')]
    lines = []
    for n, (who, t0, t1, cam, text) in enumerate(plan, 1):
        h = H[who]; ids = list(dict.fromkeys(list(h.get('emotions', {}).values())))
        st = ids[(n * 3) % len(ids)] if ids and n > 1 else h.get('default')
        lines.append({'i': n, 'who': who, 'text': text, 't0': t0, 't1': t1, 'sec': show.get('sections', ['场景预览'])[0] if n == 1 else None, 'pre': 0,
                      'chunks': [{'t0': t0, 't1': t1 - .3, 'text': text}], 'atT': [], 'fxT': [], 'kwT': [[t0 + 1, '要点贴纸', 'gold']] if n == 1 else [],
                      'fx': [], 'st': st, 'cam': cam})
    wins = [{'open': 12.88, 'close': 18.0, 'segs': [{'t': 12.88, 'img': 'testcard.jpg', 'dur': 5.4, 'id': 'test', 'orig': False}]}]
    END = 28.0; env = {}
    for k in 'AB':
        e = [0.0] * int(END * 60)
        for r in lines:
            if r['who'] != k: continue
            for f in range(int(r['t0'] * 60), int((r['t1'] - .3) * 60)):
                e[f] = round(max(0.0, abs(math.sin(f / 60 * 2 * math.pi * 3.1)) * (0.55 + 0.4 * math.sin(f / 60 * 1.7))), 3)
        env[k] = e
    stk = {k: sorted(set(h.get('emotions', {}).values()) | {h.get(x) for x in ('default', 'eyecatch', 'cover_sticker') if h.get(x)}) for k, h in H.items()}
    show_pub = {'hosts': {k: {kk: vv for kk, vv in h.items() if kk != 'card'} for k, h in H.items()}, 'channel': show.get('channel', {}),
                'show_name': show.get('show_name', ''), 'studio': show.get('studio', {}), 'animation': show.get('animation', {}),
                'effects': show.get('effects', {}), 'ui': show.get('ui', {}), 'scene': show.get('scene', {})}
    ep_pub = {'sting_sub': '', 'ticker': ['场景预览', '这里是滚动快讯', '颜色和位置都能在 show.json 里改'], 'date': time.strftime('%Y-%m-%d') + ' 20:00',
              'section0': '场景预览', 'hook_end': None, 'sting_t': -10, 'hook_total': 0, 'hook_title': ''}
    return {'end': END, 'lines': lines, 'wins': wins, 'env': env, 'stk': stk, 'show': show_pub, 'ep': ep_pub}


def cmd_scene(a):
    """Preview the show pack's studio without any episode: renders 6 shots into <节目包>/场景预览.jpg."""
    import tempfile
    from PIL import Image, ImageDraw
    sdir = os.path.abspath(a.show or (os.path.join(os.path.dirname(KIT), '节目包')))
    if not os.path.exists(os.path.join(sdir, 'show.json')): raise SystemExit(f'{sdir} 里没有 show.json（用 --show 指定节目包文件夹）')
    show = load_json(os.path.join(sdir, 'show.json'))
    for x in check_scene(sdir, show): print('  ⚠ 场景：' + x)
    site = tempfile.mkdtemp(prefix='scene_preview_')
    try:
        copy_engine(site, sdir, show); copy_scene(sdir, show, site); copy_brand(sdir, show, site)
        st = os.path.join(site, 'stk'); os.makedirs(st, exist_ok=True)
        for f in glob.glob(os.path.join(sdir, show.get('stickers_dir', '贴纸'), '*.png')): shutil.copy(f, st)
        # a test card for the screen: colour bands + frame marks, so you can see how footage sits
        tc = Image.new('RGB', (1280, 720)); dr = ImageDraw.Draw(tc)
        for k, col in enumerate([(232, 41, 59), (255, 160, 40), (255, 216, 74), (69, 224, 208), (47, 134, 240), (122, 75, 240), (30, 30, 40)]):
            dr.rectangle([k * 183, 0, (k + 1) * 183, 720], fill=col)
        dr.rectangle([0, 0, 1279, 719], outline=(255, 255, 255), width=10); dr.line([0, 0, 1280, 720], fill=(255, 255, 255), width=4); dr.line([0, 720, 1280, 0], fill=(255, 255, 255), width=4)
        fnt = cjk_font(72)
        if fnt: dr.text((640, 360), '实机画面 16:9', fill=(255, 255, 255), font=fnt, anchor='mm', stroke_width=6, stroke_fill=(0, 0, 0))
        tc.save(os.path.join(site, 'testcard.jpg'), quality=90)
        save_json(os.path.join(site, 'film.json'), scene_film(show))
        srv = Server(site, a.port)
        if a.export:
            try:
                out = os.path.join(site, 'layers')
                sh(['node', os.path.join(HERE, 'render.js'), f'http://127.0.0.1:{srv.port}/film.html', 'layers', out], cwd=HERE)
            finally:
                srv.stop()
            dd = os.path.join(sdir, show.get('scene', {}).get('dir', '场景')); os.makedirs(dd, exist_ok=True)
            from PIL import Image as _I
            names = {'back': '导出_背景.png', 'front': '导出_前景.png', 'guide': '导出_参考线.png'}
            for k, n in names.items(): shutil.copy(os.path.join(out, k + '.png'), os.path.join(dd, n))
            g = _I.open(os.path.join(out, 'guide.png')).convert('RGBA'); b = _I.open(os.path.join(out, 'back.png')).convert('RGBA')
            b.alpha_composite(_I.open(os.path.join(out, 'front.png')).convert('RGBA')); b.alpha_composite(g); b.convert('RGB').save(os.path.join(dd, '导出_合成参考.jpg'), quality=90)
            print(f'已导出到 {dd}：' + '、'.join(names.values()) + '、导出_合成参考.jpg')
            print('  在绘图软件里以「导出_背景.png」「导出_前景.png」为底改画（参考线图层可以叠在最上面对位），改完把 show.json → scene 改成 "type": "image"。')
            return
        try:
            out = os.path.join(site, 'stills'); ts = ['3', '7', '11', '13.3', '16', '21']
            sh(['node', os.path.join(HERE, 'render.js'), f'http://127.0.0.1:{srv.port}/film.html', 'stills', out] + ts, cwd=HERE)
        finally:
            srv.stop()
        names = ['全景', '主播 A 近景', '主播 B 近景', '推进大屏（途中）', '大屏全屏', '倾斜镜头']
        tw, th = 800, 450; sheet = Image.new('RGB', (tw * 3, th * 2)); fl = cjk_font(30)
        for k, t in enumerate(ts):
            im = Image.open(os.path.join(out, f'still_{t}.jpg')).resize((tw, th)); d = ImageDraw.Draw(im)
            d.rectangle([0, 0, tw - 1, th - 1], outline=(0, 0, 0), width=2)
            d.text((14, 10), names[k] if fl else f'shot {k + 1}', fill=(255, 255, 0), font=fl, stroke_width=3, stroke_fill=(0, 0, 0))
            sheet.paste(im, ((k % 3) * tw, (k // 3) * th))
        dst = os.path.join(sdir, '场景预览.jpg'); sheet.save(dst, quality=88)
        shutil.copy(os.path.join(out, 'still_3.jpg'), os.path.join(sdir, '场景预览_全景.jpg'))
        print(f'场景预览 -> {dst}（6 个镜头）和 场景预览_全景.jpg（原尺寸）')
        miss = [f for k, h in show['hosts'].items() for f in scene_film(show)['stk'][k] if not os.path.exists(os.path.join(sdir, show.get('stickers_dir', '贴纸'), f"{h['sticker_prefix']}_{f}.png"))]
        if miss: print(f'  （有 {len(miss)} 张贴纸还没画，预览里用的是占位小人）')
    finally:
        shutil.rmtree(site, ignore_errors=True)


def cmd_render(a):
    c = Ctx(a.ep)
    site = prepare_site(c)
    film = load_json(os.path.join(site, 'film.json'))
    srv = Server(site, a.port); port = srv.port
    try:
        rjs = os.path.join(HERE, 'render.js')
        if a.stills:
            out = os.path.join(c.work, 'stills'); os.makedirs(out, exist_ok=True)
            sh(['node', rjs, f'http://127.0.0.1:{port}/film.html', 'stills', out] + a.stills.split(','), cwd=HERE)
            print('截图在 work/stills/'); return
        fr = os.path.join(c.work, 'frames')
        if a.range:
            s0, s1 = [float(x) for x in a.range.split(',')]; f0, f1 = int(s0 * FPS), int(s1 * FPS)
        else:
            f0, f1 = 0, int(film['end'] * FPS)
            if not a.keep: shutil.rmtree(fr, ignore_errors=True)
            else:   # resume: only the span that is still missing
                miss = [i for i in range(f0, f1) if not os.path.exists(os.path.join(fr, f'{i:05d}.jpg'))]
                if not miss: print('帧都在，不用渲染'); return
                f0, f1 = miss[0], miss[-1] + 1
                print(f'续渲：缺 {len(miss)} 帧，渲染 {f0}–{f1}')
        os.makedirs(fr, exist_ok=True)
        nw = max(1, a.workers); step = math.ceil((f1 - f0) / nw)
        procs = []
        for k in range(nw):
            a0, a1 = f0 + k * step, min(f1, f0 + (k + 1) * step)
            if a0 >= a1: continue
            procs.append(subprocess.Popen(['node', rjs, f'http://127.0.0.1:{port}/film.html', 'range', fr, str(a0), str(a1)], cwd=HERE))
        t = time.time()
        while any(p.poll() is None for p in procs):
            time.sleep(20)
            done = len(glob.glob(os.path.join(fr, '*.jpg')))
            print(f'  渲染中 共有 {done} 帧（本次 {f0}–{f1}），{time.time()-t:.0f}s', flush=True)
        if any(p.returncode for p in procs): raise SystemExit('渲染进程出错，看上面的报错')
        if a.range:
            out = os.path.join(c.work, f'preview_{int(s0)}_{int(s1)}.mp4')
            sh(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-start_number', str(f0), '-i', os.path.join(fr, '%05d.jpg'),
                '-ss', str(s0), '-t', str(s1 - s0), '-i', os.path.join(c.work, 'master.wav'), '-map', '0:v', '-map', '1:a', '-c:v', 'libx264',
                '-preset', 'veryfast', '-crf', '24', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', out])
            print('预览:', out)
        print(f'渲染完成，用时 {time.time()-t:.0f}s')
    finally:
        srv.stop()


# ------------------------------------------------------------------ encode + split + chapters
def cmd_encode(a):
    c = Ctx(a.ep)
    film = load_json(os.path.join(c.work, 'film.json'))
    END = film['end']
    st = film['ep'].get('sting_t') or 0
    first_after_hook = next((r['i'] for r in film['lines'] if not r.get('hook')), None) if st else None
    secs = [(r['sec'], 0 if not i else (st if r['i'] == first_after_hook else max(0, r['t0'] - 1.35 - (r.get('pre') or 0))))
            for i, r in enumerate(film['lines']) if r.get('sec')]
    if not secs or secs[0][1] > 0: secs = [(film['lines'][0].get('sec') or '开场', 0)] + [s for s in secs if s[1] > 0]
    name = c.ep.get('output_name', c.show.get('show_name', 'show') + '_' + c.ep.get('version', '')) + (f'_{a.tag}' if a.tag else '')
    nf = int(END * FPS); fr = os.path.join(c.work, 'frames')
    miss = [i for i in range(nf) if not os.path.exists(os.path.join(fr, f'{i:05d}.jpg'))]
    if miss:
        raise SystemExit(f'帧不全：缺 {len(miss)}/{nf} 帧（第一个缺的是 {miss[0]}）。先跑 render（中断过就用 render --keep 续渲）')
    outd = c.p('成片'); os.makedirs(outd, exist_ok=True)
    full = os.path.join(c.work, 'full.mp4')
    cuts = [round(t + 0.65, 2) for _, t in secs[1:]]  # inside the eyecatch (fully covered)
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(c.work, 'frames', '%05d.jpg'), '-i', os.path.join(c.work, 'master.wav'),
        '-c:v', 'libx264', '-preset', a.preset, '-crf', str(a.crf), '-maxrate', a.maxrate, '-bufsize', '4M', '-pix_fmt', 'yuv420p', '-g', '120',
        '-force_key_frames', ','.join(map(str, cuts)) or '0', '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', full])
    size = os.path.getsize(full) / 1e6
    lim = float(c.ep.get('split_mb', 0) or 0)
    lines = [f"{int(t)//60:02d}:{int(t)%60:02d} {s}" for s, t in secs]
    open(os.path.join(outd, '章节.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('章节:\n' + '\n'.join(lines))
    if not lim or size <= lim:
        shutil.copy(full, os.path.join(outd, name + '.mp4')); print(f'成片 {size:.1f}MB -> 成片/{name}.mp4'); return
    rate = size / END
    chosen, s0 = [], 0
    cand = cuts + [END]
    for k, ct in enumerate(cand[:-1]):
        if (cand[k + 1] - s0) * rate > lim * 0.92:
            chosen.append(ct); s0 = ct
    tmp = os.path.join(c.work, 'part%d.mp4')
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', full, '-c', 'copy', '-map', '0', '-f', 'segment', '-segment_times', ','.join(map(str, chosen)), '-reset_timestamps', '1', tmp])
    for k in range(len(chosen) + 1):
        dst = os.path.join(outd, f'{name}_第{k+1}段.mp4')
        sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp % k, '-c', 'copy', '-movflags', '+faststart', dst])
        print(f'{os.path.basename(dst)}  {os.path.getsize(dst)/1e6:.1f}MB')
    print(f'完整版在 work/full.mp4（{size:.1f}MB）')


# ------------------------------------------------------------------ cover
def cmd_cover(a):
    c = Ctx(a.ep)
    cv = c.ep.get('cover', {})
    cd = os.path.join(c.work, 'cover'); os.makedirs(cd, exist_ok=True)
    tpl = open(os.path.join(KIT, 'templates', 'cover', 'cover.html'), encoding='utf-8').read()
    # background frame
    bg = cv.get('bg_image')
    from PIL import Image, ImageFilter, ImageEnhance
    if bg and os.path.exists(c.p(bg)):
        im = Image.open(c.p(bg)).convert('RGB')
    else:
        cid, fr = cv.get('bg_clip', 'w00s0'), int(cv.get('bg_frame', 60))
        f = os.path.join(c.work, 'site', 'clipf', cid, f'{fr:05d}.jpg')
        im = Image.open(f).convert('RGB') if os.path.exists(f) else Image.new('RGB', (1280, 720), (30, 60, 140))
        crop = cv.get('bg_crop', [0, 95, 1280, 585]); im = im.crop(tuple(crop))
    W, Hh = 1920, 1200; s = max(W / im.width, Hh / im.height); im = im.resize((int(im.width * s), int(im.height * s)))
    x = (im.width - W) // 2; im = im.crop((x, 0, x + W, Hh)).filter(ImageFilter.GaussianBlur(2)); im.save(os.path.join(cd, 'bg.jpg'), quality=92)
    for key, fn in [('game_logo', 'logo.png')]:
        p = c.show.get('channel', {}).get(key)
        if p and os.path.exists(c.sp(p)): shutil.copy(c.sp(p), os.path.join(cd, fn))
    H = c.show['hosts']
    for k, h in H.items():
        sid = cv.get(f'sticker_{k}', h.get('cover_sticker', h.get('default')))
        src = os.path.join(c.sp(c.show['stickers_dir']), f"{h['sticker_prefix']}_{sid}.png")
        if os.path.exists(src): shutil.copy(src, os.path.join(cd, f'host{k}.png'))
    data = {'game': c.show.get('game', ''), 'game_en': c.show.get('game_en', ''), 'version': c.ep.get('version', ''),
            'kicker': cv.get('kicker', '特别报道'), 'sub': cv.get('sub', '前瞻全速报'), 'info': cv.get('info', []), 'gift': cv.get('gift', ''),
            'gift_note': cv.get('gift_note', ''), 'foot': cv.get('foot', ''), 'hot': cv.get('hot_index', 2), 'ver_label': cv.get('ver_label', 'VER.'),
            'special': cv.get('special', 'SPECIAL')}
    outs = []
    for ratio, (w, h) in {'16x9': (1920, 1080), '4x3': (1600, 1200)}.items():
        html = tpl.replace('/*DATA*/null', json.dumps(dict(data, ratio=ratio, W=w, H=h), ensure_ascii=False))
        hp = os.path.join(cd, f'cover_{ratio}.html'); open(hp, 'w', encoding='utf-8').write(html)
        png = c.p(os.path.join('成片', f'封面_{ratio}' + (f'_{a.tag}' if a.tag else '') + '.png'))
        import pathlib
        sh(['node', os.path.join(HERE, 'shot.js'), pathlib.Path(hp).resolve().as_uri(), png, str(w), str(h)], cwd=HERE)
        outs.append(png)
    print('封面:', *outs, sep='\n  ')


# ------------------------------------------------------------------ qa
def cmd_qa(a):
    c = Ctx(a.ep)
    film = load_json(os.path.join(c.work, 'film.json')); tl = load_json(os.path.join(c.work, 'timeline.json'))
    probs = []
    if tl.get('overlap_10ms'): probs.append(f"两人声音重叠 {tl['overlap_10ms']*10}ms")
    for w in film['wins']:
        for s in w['segs']:
            if not s.get('dir'): probs.append(f"片段 {s['id']} 没有画面（缺文件或没跑 prepclips）")
            elif s['n'] < s['dur'] * FPS - 15: probs.append(f"片段 {s['id']} 太短：{s['n']/FPS:.1f}s < 需要 {s['dur']:.1f}s（最后一帧会定格）")
    for r in film['lines']:
        if r['chunks'] and any(not ch['text'].strip() for ch in r['chunks']): probs.append(f"第{r['i']}句 有空字幕")
    used = {'A': set(), 'B': set()}
    for r in film['lines']:
        oth = 'B' if r['who'] == 'A' else 'A'
        if r.get('st'): used[r['who']].add(r['st'])
        if r.get('re'): used[oth].add(r['re'])
        for _, w, sid in r.get('atT', []): used[w].add(sid)
    for k, h in c.show['hosts'].items():
        used[k].add(h.get('default'))
        lack = sorted(x for x in used[k] if x and not os.path.exists(os.path.join(c.sp(c.show['stickers_dir']), f"{h['sticker_prefix']}_{x}.png")))
        if lack: probs.append(f"{h['name']} 有 {len(lack)} 张贴纸是占位图：" + '、'.join(f"{h['sticker_prefix']}_{x}.png" for x in lack) + '（画好放进贴纸文件夹后重新 render）')
    ts = [0.6]
    for r in film['lines']:
        if r.get('sec'): ts.append(round(r['t0'] - 0.8, 2)); ts.append(round(r['t0'] + 0.8, 2))
    for w in film['wins']: ts += [round(w['open'] + 1.2, 2), round(w['close'] + 1.0, 2)]
    ts = sorted({t for t in ts if 0 < t < film['end']})[:40]
    fr = os.path.join(c.work, 'frames')
    nf = int(film['end'] * FPS); have = len(glob.glob(os.path.join(fr, '*.jpg')))
    if have < nf: probs.append(f'渲染帧不全（{have}/{nf}）：关键帧拼图会缺格。qa 要在全片 render 之后跑')
    from PIL import Image, ImageDraw
    tiles = []
    for t in ts:
        f = os.path.join(fr, f'{int(t*FPS):05d}.jpg')
        if os.path.exists(f):
            im = Image.open(f).resize((480, 270)); ImageDraw.Draw(im).text((8, 250), f'{t:.1f}s', fill=(255, 255, 0)); tiles.append(im)
    if not tiles:
        probs.append('还没有渲染帧（work/frames 为空），关键帧拼图跳过；先跑 render')
    if tiles:
        cols = 4; rows = math.ceil(len(tiles) / cols); sheet = Image.new('RGB', (cols * 480, rows * 270))
        for k, im in enumerate(tiles): sheet.paste(im, ((k % cols) * 480, (k // cols) * 270))
        sheet.save(os.path.join(c.work, 'qa_关键帧.jpg'), quality=85)
        print('关键帧拼图: work/qa_关键帧.jpg（请逐格查看：字幕完整、人物不透到大屏上、台标清楚、片段不是官方主持人画面）')
    print('自检问题:' if probs else '自检：没发现问题'); [print('  ⚠', p) for p in probs]


def cmd_all(a):
    for f in [cmd_align, cmd_stage, cmd_prepclips, cmd_audio, cmd_render, cmd_encode, cmd_cover, cmd_qa]:
        print(f'\n==== {f.__name__[4:]} ===='); f(a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd'); ap.add_argument('--ep', default='.'); ap.add_argument('--show')
    ap.add_argument('--workers', type=int, default=max(1, min(4, (os.cpu_count() or 2)))); ap.add_argument('--range'); ap.add_argument('--stills')
    ap.add_argument('--keep', action='store_true'); ap.add_argument('--cut', action='store_true'); ap.add_argument('--force', action='store_true')
    ap.add_argument('--port', type=int, default=8765); ap.add_argument('--crf', type=int, default=25); ap.add_argument('--preset', default='veryfast')
    ap.add_argument('--maxrate', default='1.6M'); ap.add_argument('--in', dest='inp')
    ap.add_argument('--tag', help='改版时给成片/封面文件名加后缀，如 v2'); ap.add_argument('--version', help='init: 版本号，如 2.1')
    ap.add_argument('--root', help='setup: 工作区（项目文件夹），默认是工具包的上一级'); ap.add_argument('--update', action='store_true', help='setup: 用安装包里的新版覆盖工具包（节目包不覆盖）')
    ap.add_argument('--install', action='store_true', help='setup: 自动安装缺的 python 库和 playwright')
    ap.add_argument('--export', action='store_true', help='scene: 把当前场景导出成背景/前景/参考线 PNG，方便在绘图软件里改')
    a = ap.parse_args()
    fn = globals().get('cmd_' + a.cmd)
    if not fn: raise SystemExit(__doc__)
    fn(a)


if __name__ == '__main__':
    main()
