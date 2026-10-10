"""Text helpers: Arabic numbers -> spoken Chinese, normalisation for matching."""
import re

DIG = '零一二三四五六七八九'


def _int_cn(n, liang=True):
    if n == 0:
        return '零'
    units = [(10**8, '亿'), (10**4, '万')]
    out = ''
    for base, name in units:
        if n >= base:
            out += _int_cn(n // base, liang) + name
            n %= base
            if 0 < n < base // 10:
                out += '零'
    small = ''
    started = False
    for base, name in [(1000, '千'), (100, '百'), (10, '十'), (1, '')]:
        d = n // base
        n %= base
        if d:
            if base == 10 and d == 1 and not started and not out:
                small += '十'
            else:
                ch = DIG[d]
                if d == 2 and liang and base >= 100:
                    ch = '两'
                small += ch + name
            started = True
        elif started and n:
            if not small.endswith('零'):
                small += '零'
    res = out + small
    if res.startswith('二') and len(res) > 1 and res[1] in '百千万亿' and liang:
        res = '两' + res[1:]
    return res


def num_to_cn(m):
    s = m.group(0)
    nxt = m.string[m.end():].lstrip()[:1]
    prv = m.string[:m.start()].rstrip()[-1:]
    if s == '2' and nxt and nxt in '个位套次张天周名把只件款种条段项部抽连发轮倍层座本首期' and prv != '第':
        return '两'
    if '.' in s:
        a, b = s.split('.', 1)
        return _int_cn(int(a)) + '点' + ''.join(DIG[int(c)] for c in b)
    n = int(s)
    if len(s) >= 5 and s.startswith('20') and False:
        return ''.join(DIG[int(c)] for c in s)
    return _int_cn(n)


SPECIAL = [(r'(?i)(?<![a-z])1v1(?![a-z])', '一对一'), (r'(?i)(?<![a-z])1v2(?![a-z])', '一对二')]


def to_spoken(text):
    """Text that goes to the voice actor / TTS: numbers become Chinese words."""
    t = text
    for a, b in SPECIAL:
        t = re.sub(a, b, t)
    # years like 2026 read digit by digit
    t = re.sub(r'(?<!\d)((?:19|20)\d\d)(?=\s*年)', lambda m: ''.join(DIG[int(c)] for c in m.group(1)), t)
    # percentages (fractions / 9/24-style dates are ambiguous: write them in Chinese in the script)
    t = re.sub(r'(\d+(?:\.\d+)?)\s*%', lambda m: '百分之' + m.group(1), t)
    t = re.sub(r'\d+(\.\d+)?', num_to_cn, t)
    t = re.sub(r'(?<=[一-鿿])\s+(?=[一-鿿])', '', t)
    t = re.sub(r'(?<=[一-鿿])\s+|\s+(?=[一-鿿])', '', t)
    return t.strip()


def norm(text):
    """For matching: spoken form, drop everything that is not a letter/digit/CJK."""
    return re.sub(r'[^\w]', '', to_spoken(text)).lower()


PUNCT_SPLIT = re.compile(r'(?<=[，。！？；：、…—,!?;])')


def phrases(text, cap=22):
    """Split a spoken line into subtitle phrases (keep punctuation); phrases longer than `cap` chars are cut."""
    parts = [p for p in PUNCT_SPLIT.split(text) if p.strip()]
    out = []
    for p in parts:
        if out and len(re.sub(r'[^\w]', '', p)) <= 1:
            out[-1] += p
        elif out and len(re.sub(r'[^\w]', '', out[-1])) < 5:
            out[-1] += p
        else:
            out.append(p)
    # cap phrase length for the subtitle bar
    res = []
    for p in out:
        while len(p) > cap:
            cut = max(4, cap - 4)
            res.append(p[:cut]); p = p[cut:]
        res.append(p)
    return [p.strip() for p in res if p.strip()]


if __name__ == '__main__':
    for s in ['第 2 个', '2 抽', '2026 年', '50%', '2 个', '1v1 对战', '1.4 分上下半', '白送 20 抽，外加 200 万金币', '9 月 24 号开到 10 月 15 号', '一共 1000 层，每 10 层', '1v1 对战', '200万', '12 抽', '2 个', '105', '1010']:
        print(s, '->', to_spoken(s))
