"""spec.json を SVG に描画するレイアウトエンジン。

- ブラウザ不要（標準ライブラリのみ）。プレビューも Figma 書き出しも同じ SVG を使うので、見た目が食い違わない
- 座標はすべて実機 375pt 幅の pt。出力時に scale を掛ける（既定 3 → 1125px）
- 実機の寸法（本文14 / 左右余白20）は invy の実機 CSS に合わせる
- 見た目は campaign-design-dip の紹介ページ画面に揃える：色面のヒーロー、白の角丸カード、
  リボン見出し＋大きな数字の特典、チェック付きの箇条書き、番号付きのステップ、塗りの CTA
- テキストは行ごとに改行位置を確定させて出す（Figma 側でフォント差による折り返しズレが起きない）
- 出力は4種類：紹介者ページ／ゲストページ（ブロックを縦に積む）、OGP 画像、LINE での表示イメージ
"""
import base64, mimetypes, os, re
from catalog import BLOCKS

W = 375            # 実機幅（pt）
PAD_X = 20         # 左右余白
PAD_Y = 36         # セクション上下余白
CW = W - PAD_X * 2  # 335

LINE_GREEN = '#06C755'   # LINE ボタン
REQ_RED = '#E0474C'


# ---------------------------------------------------------------- 色
def _rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """a と b を t（0=a, 1=b）で混ぜる"""
    ra, rb = _rgb(a), _rgb(b)
    return '#' + ''.join(f'{round(x + (y - x) * t):02X}' for x, y in zip(ra, rb))


def lum(h):
    r, g, b = (v / 255 for v in _rgb(h))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def on(h):
    """地色の上に載せる文字色（白か墨）"""
    return '#FFFFFF' if lum(h) < 0.45 else '#1C1E22'


DEFAULT_PRIMARY, DEFAULT_SECONDARY = '#D8232A', '#3E6C8F'   # campaign-design-dip の scarlet / sky


def theme_of(spec):
    th = dict(spec.get('theme') or {})
    wire = th.get('mode') == 'wire'
    primary = th.get('primary') or ('#3B3F45' if wire else DEFAULT_PRIMARY)
    secondary = th.get('secondary') or ('#8A9096' if wire else DEFAULT_SECONDARY)
    t = dict(
        primary=primary, secondary=secondary,
        onPrimary=on(primary), onSecondary=on(secondary),
        deep=mix(primary, '#000000', 0.28),               # 大きな数字・強調見出し
        tint=mix(primary, '#FFFFFF', 0.9),                # 淡い面（クーポン枠）
        soft=mix(secondary, '#FFFFFF', 0.91),             # セクションの交互背景
        point=mix(primary, '#FFFFFF', 0.92),              # ポイント（チェック箇条書き）の面
        cream='#EEF0F2' if wire else '#FFF3D6',           # 吹き出し・帯
        ink='#1C1E22', body='#3B3F45', mute='#767C83', line='#E4E7EA',
        bg='#FFFFFF', field='#F6F7F8', note='#F4F5F6', footer='#1C1E22', onFooter='#C4C9CE',
        ph=mix(secondary, '#FFFFFF', 0.82), phInk=mix(secondary, '#FFFFFF', 0.35),
        radius=10, font='Noto Sans JP', headFont='Noto Sans JP',
        lineBtn=LINE_GREEN, mail=primary, link=mix(primary, '#FFFFFF', 0.28))
    for k, v in th.items():
        if k in t and v:
            t[k] = v
    return t


# ---------------------------------------------------------------- テキスト計測
NO_START = set('、。，．,.・：；:;？！?!ー－―…‥」』）)］]｝}〉》】〕ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々')
NO_END = set('「『（(［[｛{〈《【〔')
TOKEN = re.compile(r'[A-Za-z0-9@#%&+\-_/.:,\'"]+|.', re.S)


def char_w(ch, size):
    o = ord(ch)
    if ch == ' ':
        return size * 0.28
    if o < 0x80:
        if ch in "il.,:;|!'`":
            return size * 0.28
        if ch in 'mwMW':
            return size * 0.82
        if ch.isdigit():
            return size * 0.58
        if ch.isupper():
            return size * 0.66
        return size * 0.55
    if 0xFF61 <= o <= 0xFF9F:
        return size * 0.5
    return size * 1.0


def text_w(s, size, ls=0):
    return sum(char_w(c, size) + ls for c in str(s))


def wrap(text, size, maxw, ls=0):
    lines = []
    for para_ in str(text or '').split('\n'):
        line = ''
        for tok in TOKEN.findall(para_):
            tw = text_w(tok, size, ls)
            if text_w(line, size, ls) + tw <= maxw or not line:
                if tw > maxw and len(tok) > 1:          # 長い英数字は文字単位で割る
                    for ch in tok:
                        if text_w(line + ch, size, ls) > maxw and line:
                            lines.append(line); line = ''
                        line += ch
                else:
                    line += tok
            elif tok in NO_START:                        # 行頭禁則：ぶら下げ
                line += tok
            else:
                carry = ''
                while line and line[-1] in NO_END:        # 行末禁則：次行へ送る
                    carry = line[-1] + carry; line = line[:-1]
                lines.append(line); line = carry + tok
        lines.append(line)
    return lines


def xesc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;').replace("'", '&apos;'))


# ---------------------------------------------------------------- SVG キャンバス
class Canvas:
    def __init__(self, scale, theme, base_dir):
        self.S = scale; self.t = theme; self.base = base_dir
        self.out = []; self.ids = {}; self.warn = []

    def n(self, v):
        v = v * self.S
        return str(int(round(v))) if abs(v - round(v)) < 1e-6 else f'{v:.1f}'

    def uid(self, name):
        if not name:
            return ''
        k = self.ids.get(name, 0) + 1; self.ids[name] = k
        return f' id="{xesc(name if k == 1 else f"{name}-{k}")}"'

    def open(self, name, transform=None):
        tr = f' transform="{transform}"' if transform else ''
        self.out.append(f'<g{self.uid(name)}{tr}>')

    def close(self):
        self.out.append('</g>')

    def mark(self):
        return len(self.out)

    def cut(self, m):
        body = self.out[m:]; del self.out[m:]
        return body

    def rect(self, x, y, w, h, fill=None, stroke=None, sw=1, rx=0, name=None, opacity=None, dash=None):
        a = f'<rect{self.uid(name)} x="{self.n(x)}" y="{self.n(y)}" width="{self.n(w)}" height="{self.n(h)}"'
        if rx:
            a += f' rx="{self.n(min(rx, h / 2, w / 2))}"'
        a += f' fill="{fill or "none"}"'
        if opacity is not None:
            a += f' fill-opacity="{opacity}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{self.n(sw)}"'
            if dash:
                a += f' stroke-dasharray="{self.n(dash)} {self.n(dash)}"'
        self.out.append(a + '/>')

    def line(self, x1, y1, x2, y2, stroke, sw=1, dash=None):
        d = f' stroke-dasharray="{self.n(dash)} {self.n(dash)}"' if dash else ''
        self.out.append(f'<line x1="{self.n(x1)}" y1="{self.n(y1)}" x2="{self.n(x2)}" y2="{self.n(y2)}" '
                        f'stroke="{stroke}" stroke-width="{self.n(sw)}" stroke-linecap="round"{d}/>')

    def circle(self, cx, cy, r, fill=None, stroke=None, sw=1, name=None, opacity=None):
        a = f'<circle{self.uid(name)} cx="{self.n(cx)}" cy="{self.n(cy)}" r="{self.n(r)}" fill="{fill or "none"}"'
        if opacity is not None:
            a += f' fill-opacity="{opacity}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{self.n(sw)}"'
        self.out.append(a + '/>')

    def ellipse(self, cx, cy, rx, ry, fill, name=None):
        self.out.append(f'<ellipse{self.uid(name)} cx="{self.n(cx)}" cy="{self.n(cy)}" rx="{self.n(rx)}" '
                        f'ry="{self.n(ry)}" fill="{fill}"/>')

    def path(self, d, fill='none', stroke=None, sw=1, name=None):
        """d は pt 座標の [('M', x, y), ('L', x, y), ('Z',)] のリスト"""
        seg = [p[0] + ' '.join(self.n(v) for v in p[1:]) for p in d]
        s = (f' stroke="{stroke}" stroke-width="{self.n(sw)}" stroke-linecap="round" stroke-linejoin="round"'
             if stroke else '')
        self.out.append(f'<path{self.uid(name)} d="{" ".join(seg)}" fill="{fill}"{s}/>')

    def text(self, x, y, w, s, size=14, weight=400, color=None, align='left', lh=1.75, head=False,
             name=None, ls=0, maxlines=None, warn=True):
        """折り返して描画し、使った高さ（pt）を返す。空文字なら 0。"""
        if s is None or str(s).strip() == '':
            return 0
        lines = wrap(s, size, w, ls)
        if maxlines and len(lines) > maxlines:
            lines = lines[:maxlines]; lines[-1] = lines[-1][:-1] + '…'
        if warn:
            for ln in lines:
                if text_w(ln, size, ls) > w + size * 1.2:
                    self.warn.append(f'はみ出し: 「{ln[:16]}…」')
            if head and len(lines) > 1 and 0 < len(lines[-1].strip()) <= 2:
                self.warn.append(f'見出しの泣き別れ: 「…{lines[-2][-6:]}／{lines[-1]}」→ 改行位置（\\n）か文言を調整')
        fam = self.t['headFont'] if head else self.t['font']
        lhp = size * lh
        anchor, tx = 'start', x
        if align == 'center':
            anchor, tx = 'middle', x + w / 2
        elif align == 'right':
            anchor, tx = 'end', x + w
        spans = ''.join(
            f'<tspan x="{self.n(tx)}" y="{self.n(y + i * lhp + (lhp - size) / 2 + size * 0.86)}">{xesc(l)}</tspan>'
            for i, l in enumerate(lines))
        lsa = f' letter-spacing="{self.n(ls)}"' if ls else ''
        self.out.append(f'<text{self.uid(name)} font-family="{xesc(fam)}" font-size="{self.n(size)}" '
                        f'font-weight="{weight}" fill="{color or self.t["body"]}" text-anchor="{anchor}"{lsa} '
                        f'xml:space="preserve">{spans}</text>')
        return len(lines) * lhp

    def runs(self, cx, y, parts, name=None):
        """1行に大きさの違う文字を中央揃えで並べる（例：5,000 ＋ 円分）。parts = [(文字, size, weight, color)]。高さを返す"""
        parts = [p for p in parts if p[0]]
        if not parts:
            return 0
        big = max(p[1] for p in parts)
        # 太字の大きな数字はフォント差で幅が読みにくいので、広めに見積もり、要素の間にすき間を取る（重なり防止）
        wd = lambda s, size: text_w(s, size) * 1.12
        gap = big * 0.12
        x = cx - (sum(wd(p[0], p[1]) for p in parts) + gap * (len(parts) - 1)) / 2
        base = y + big * 0.95
        self.open(name or '文字組み')
        for s, size, weight, color in parts:
            self.out.append(f'<text font-family="{xesc(self.t["headFont"])}" font-size="{self.n(size)}" '
                            f'font-weight="{weight}" fill="{color}" xml:space="preserve">'
                            f'<tspan x="{self.n(x)}" y="{self.n(base)}">{xesc(s)}</tspan></text>')
            x += wd(s, size) + gap
        self.close()
        return big * 1.2

    def image(self, x, y, w, h, src, label, name=None, fit='cover', rx=None):
        if src:
            p = src if os.path.isabs(src) else os.path.join(self.base, src)
            if os.path.exists(p):
                mt = mimetypes.guess_type(p)[0] or 'image/png'
                with open(p, 'rb') as f:
                    data = base64.b64encode(f.read()).decode()
                par = 'xMidYMid slice' if fit == 'cover' else 'xMidYMid meet'
                self.out.append(f'<image{self.uid(name or label)} x="{self.n(x)}" y="{self.n(y)}" width="{self.n(w)}" '
                                f'height="{self.n(h)}" preserveAspectRatio="{par}" '
                                f'href="data:{mt};base64,{data}" xlink:href="data:{mt};base64,{data}"/>')
                return
            self.warn.append(f'画像が見つからない: {src}')
        t = self.t
        self.open(name or f'画像枠_{label}')
        self.rect(x, y, w, h, fill=t['ph'], rx=t['radius'] if rx is None else rx)
        if w >= 40 and h >= 30:                                   # 画像アイコン（枠＋太陽＋山）
            s = min(26, w * 0.3, h * 0.36)
            ix, iy = x + w / 2 - s / 2, y + h / 2 - s / 2 - (7 if h >= 70 else 0)
            self.rect(ix, iy, s, s * 0.8, stroke=t['phInk'], sw=1.3, rx=s * 0.12)
            self.circle(ix + s * 0.3, iy + s * 0.28, s * 0.09, fill=t['phInk'])
            self.path([('M', ix + s * 0.12, iy + s * 0.68), ('L', ix + s * 0.4, iy + s * 0.44),
                       ('L', ix + s * 0.6, iy + s * 0.6), ('L', ix + s * 0.72, iy + s * 0.5),
                       ('L', ix + s * 0.88, iy + s * 0.66)], stroke=t['phInk'], sw=1.3)
            if h >= 70 and w >= 90:
                self.text(x + 6, iy + s * 0.8 + 6, w - 12, label, 10, 500, t['phInk'], 'center', 1.5,
                          maxlines=1, warn=False)
        self.close()


# ---------------------------------------------------------------- 部品
def img_of(b, slot):
    return (b.get('images') or {}).get(slot)


def slot_size(b, prefix):
    for s, _, w, h in BLOCKS[b['type']].get('images', []):
        if s.replace('{i}', '') == prefix:
            return w, h
    return CW, 200


def icon(c, kind, cx, cy, col):
    """ボタン用の小さなアイコン（LINE／メール／リンク）"""
    if kind == 'line':
        c.circle(cx, cy, 10, fill='#FFFFFF')
        c.ellipse(cx, cy - 0.5, 6.5, 5, LINE_GREEN)
        c.path([('M', cx - 2.5, cy + 3.5), ('L', cx - 3.5, cy + 6.5), ('L', cx + 0.5, cy + 4), ('Z',)], fill=LINE_GREEN)
    elif kind == 'mail':
        c.rect(cx - 8, cy - 6, 16, 12, stroke=col, sw=1.5, rx=1.5)
        c.path([('M', cx - 7, cy - 5), ('L', cx, cy + 1), ('L', cx + 7, cy - 5)], stroke=col, sw=1.5)
    elif kind == 'link':
        c.rect(cx - 9, cy - 4, 10, 8, stroke=col, sw=1.5, rx=4)
        c.rect(cx - 1, cy - 4, 10, 8, stroke=col, sw=1.5, rx=4)


def is_line(label):
    return 'LINE' in str(label or '').upper()


def button(c, x, y, w, h, label, name='ボタン', fill=None, color=None, size=None, outline=False, pill=False,
           arrow=True, rx=None, ico=None):
    t = c.t
    if fill is None and not outline and is_line(label):   # LINE で送る動きのボタンは、どこでも同じ LINE の緑にそろえる
        fill = t.get('lineBtn', LINE_GREEN)
        ico = ico or ('line' if h >= 48 else None)
    fill = fill or t['primary']
    r = h / 2 if pill else (t['radius'] if rx is None else rx)
    if outline:
        c.rect(x, y, w, h, fill=t['bg'], stroke=fill, sw=1.5, rx=r, name=name + '_背景')
        col = color or fill
    else:
        c.rect(x, y, w, h, fill=fill, rx=r, name=name + '_背景')
        col = color or on(fill)
    fs = size or max(11, min(17, round(h * 0.25)))
    if ico:
        icon(c, ico, x + 28, y + h / 2, col)
    c.text(x + 14 + (26 if ico else 0), y + (h - fs * 1.4) / 2, w - 28 - (52 if ico else 0), label, fs, 700, col,
           'center', lh=1.4, name=name + '_文言', maxlines=1)
    if arrow and h >= 40:
        ax, ay = x + w - 20, y + h / 2
        c.path([('M', ax - 3, ay - 5), ('L', ax + 2, ay), ('L', ax - 3, ay + 5)], stroke=col, sw=1.8,
               name=name + '_矢印')
    return h


def sec_head(c, x, y, w, title, eyebrow=None, align='center', size=21, color=None, bar=True):
    """セクション見出し：小さな英字ラベル＋太字見出し＋短いバー。下の余白まで含めた高さを返す"""
    t = c.t; cy = y
    if eyebrow:
        cy += c.text(x, cy, w, eyebrow, 10.5, 700, t['primary'], align, 1.5, name='見出しラベル', ls=1.2) + 2
    h = c.text(x, cy, w, title, size, 700, color or t['ink'], align, 1.5, head=True, name='見出し')
    if not h:
        return cy - y
    cy += h
    if bar:
        bx = x + (w - 32) / 2 if align == 'center' else x
        c.rect(bx, cy + 8, 32, 3, fill=t['primary'], rx=1.5, name='見出しバー')
        cy += 11
    return cy - y + 18


def para(c, x, y, w, s, size=14, align='left', name='本文', color=None, lh=1.8):
    return c.text(x, y, w, s, size, 400, color or c.t['body'], align, lh=lh, name=name)


def card(c, x, y, w, draw, pad=18, fill=None, stroke=None, rx=None, name='カード'):
    """中身を描いてから下に角丸カードを敷く。draw(x, y, w) -> 中身の高さ。stroke='' で枠線なし"""
    t = c.t
    m = c.mark()
    h = draw(x + pad, y + pad, w - pad * 2) + pad * 2
    body = c.cut(m)
    c.rect(x, y, w, h, fill=fill or t['bg'], stroke=t['line'] if stroke is None else stroke, sw=1,
           rx=t['radius'] + 4 if rx is None else rx, name=name)
    c.out += body
    return h


def check(c, x, y, size=16, color=None):
    col = color or c.t['primary']
    c.circle(x + size / 2, y + size / 2, size / 2, fill=col)
    c.path([('M', x + size * 0.28, y + size * 0.52), ('L', x + size * 0.44, y + size * 0.68),
            ('L', x + size * 0.74, y + size * 0.34)], stroke=on(col), sw=1.6)


def num_badge(c, cx, cy, n, r=14, fill=None):
    fill = fill or c.t['primary']
    c.circle(cx, cy, r, fill=fill, name=f'番号{n}')
    c.text(cx - r, cy - r * 0.72, r * 2, str(n), r * 1.05, 700, on(fill), 'center', 1.4, warn=False)


def split_amount(s):
    """「Amazonギフト券1,000円分」→ ('Amazonギフト券', '1,000', '円分')。数字が無ければ None"""
    m = re.search(r'([\d０-９][\d０-９,，.．]*)', s or '')
    if not m:
        return None
    return s[:m.start()], m.group(1), s[m.end():]


def slides_of(d):
    return [s if isinstance(s, dict) else {'text': str(s)} for s in d.get('slides') or []] or [{'text': ''}]


# ---------------------------------------------------------------- ブロック描画
# 各関数は (canvas, block, page, y) を受け取り、ブロックの高さ（pt）を返す

def b_header(c, b, p, y):
    t, d = c.t, b['data']
    h = 50
    c.line(0, y + h - 0.5, W, y + h - 0.5, t['line'], 1)
    has_cta = d.get('ctaOn', True) not in (False, 'off', 'なし')
    center = d.get('logoPos') == 'center' or not has_cta
    if img_of(b, 'logo'):
        c.image((W - 140) / 2 if center else 14, y + 8, 140, 34, img_of(b, 'logo'), 'ロゴ', name='ロゴ', fit='contain')
    else:                                                          # ロゴ未支給：案件名の文字ロゴで仮置き
        c.text(20 if center else 16, y + 14, CW if center else 190, p.get('_project') or 'LOGO', 15, 900, t['ink'],
               'center' if center else 'left', 1.4, name='ロゴ（画像に差し替え）', maxlines=1, warn=False)
    if not has_cta:
        return h
    if d.get('ctaType') == 'image':
        c.image(W - 126, y + 8, 116, 34, img_of(b, 'ctaImg'), 'ボタン画像', name='ヘッダーボタン画像', fit='contain')
    elif d.get('btnShape') == 'square':
        c.rect(W - 110, y, 110, h - 1, fill=t['primary'], name='ヘッダーボタン_背景')
        c.text(W - 106, y + (h - 1 - 12 * 1.4) / 2, 102, d.get('cta'), 12, 700, t['onPrimary'], 'center', 1.4,
               name='ヘッダーボタン_文言', maxlines=1)
    else:
        bw = min(150, max(96, text_w(d.get('cta', ''), 11) + 30))
        button(c, W - bw - 12, y + 10, bw, 30, d.get('cta'), name='ヘッダーボタン', pill=True, size=11, arrow=False)
    return h


def hero(c, y, copy, sub, bubble):
    """色面のヒーロー（campaign-design-dip の紹介ページ画面と同じ構造）。背景は呼び出し側で敷く。高さを返す"""
    t = c.t
    cy = y + 30
    if sub:
        sw_ = min(CW, text_w(sub, 11.5) + 30)
        c.rect((W - sw_) / 2, cy, sw_, 24, fill='#000000', rx=12, opacity=0.14, name='小見出し_地')
        c.text((W - sw_) / 2, cy + 3.5, sw_, sub, 11.5, 700, t['onSecondary'], 'center', 1.5, name='小見出し')
        cy += 36
    cy += c.text(PAD_X, cy, CW, copy, 30, 900, t['onSecondary'], 'center', 1.4, head=True, name='メインコピー') + 18
    ih = 150
    c.open('イラスト枠')
    for dx in (-122, 122):
        c.circle(W / 2 + dx, cy + ih / 2 + 16, 42, fill='#FFFFFF', opacity=0.18)
        c.text(W / 2 + dx - 42, cy + ih / 2 + 8, 84, '人物イラスト', 9, 500, t['onSecondary'], 'center', 1.5, warn=False)
    c.close()
    if bubble:
        bw, bh = 156, 106
        bx, by = W / 2, cy + 6 + bh / 2
        c.open('吹き出し')
        c.path([('M', bx - 14, by + bh / 2 - 8), ('L', bx - 4, by + bh / 2 + 12), ('L', bx + 12, by + bh / 2 - 8), ('Z',)],
               fill=t['cream'])
        c.ellipse(bx, by, bw / 2, bh / 2, t['cream'])
        lines = wrap(bubble, 14.5, bw - 40)
        th_ = len(lines) * 14.5 * 1.4
        c.text(bx - bw / 2 + 20, by - th_ / 2, bw - 40, bubble, 14.5, 900, t['deep'], 'center', 1.4, name='吹き出しの文言')
        c.close()
    return cy + ih - y


def hero_photo(c, b, y):
    """写真入りのヒーロー：色面にコピー → 写真 → 写真の上端にまたがる吹き出し。高さを返す"""
    t, d = c.t, b['data']
    cy = y + 28
    if d.get('sub'):
        sw_ = min(CW, text_w(d['sub'], 11.5) + 30)
        c.rect((W - sw_) / 2, cy, sw_, 24, fill='#000000', rx=12, opacity=0.16, name='小見出し_地')
        c.text((W - sw_) / 2, cy + 3.5, sw_, d['sub'], 11.5, 700, t['onSecondary'], 'center', 1.5, name='小見出し')
        cy += 34
    cy += c.text(PAD_X, cy, CW, d.get('copy'), 29, 900, t['onSecondary'], 'center', 1.4, head=True, name='メインコピー')
    cy += 64 if d.get('bubble') else 22
    pw, ph = slot_size(b, 'photo')
    h = W * ph / pw
    c.image(0, cy, W, h, img_of(b, 'photo'), 'KV写真', name='KV写真')
    if d.get('bubble'):
        bw, bh = 170, 96
        bx, by = W / 2, cy - 4
        c.open('吹き出し')
        c.path([('M', bx - 14, by + bh / 2 - 8), ('L', bx - 2, by + bh / 2 + 14), ('L', bx + 14, by + bh / 2 - 8), ('Z',)],
               fill=t['cream'])
        c.ellipse(bx, by, bw / 2, bh / 2, t['cream'])
        lines = wrap(d['bubble'], 15, bw - 44)
        th_ = len(lines) * 15 * 1.35
        c.text(bx - bw / 2 + 22, by - th_ / 2, bw - 44, d['bubble'], 15, 900, t['deep'], 'center', 1.35,
               name='吹き出しの文言')
        c.close()
    return cy + h - y


def b_kvimg(c, b, p, y):
    d = b['data']
    if img_of(b, 'photo'):
        m = c.mark()
        h = hero_photo(c, b, y)
        body = c.cut(m)
        c.rect(0, y, W, h + 12, fill=c.t['secondary'], name='ヒーロー背景')
        c.out += body
        c.rect(0, y + h, W, 12, fill=c.t['cream'], name='帯')
        return h + 12
    if img_of(b, 'kv'):
        c.image(0, y, W, 500, img_of(b, 'kv'), 'KV画像', name='KV画像')
        return 500
    m = c.mark()
    h = hero(c, y, d.get('copy'), d.get('sub'), d.get('bubble'))
    body = c.cut(m)
    c.rect(0, y, W, h + 12, fill=c.t['secondary'], name='ヒーロー背景')
    c.out += body
    c.rect(0, y + h, W, 12, fill=c.t['cream'], name='帯')
    return h + 12


def b_kv(c, b, p, y):
    d, t = b['data'], c.t
    m = c.mark()
    cy = y + 30
    cy += c.text(PAD_X, cy, CW, d.get('eyebrow'), 12, 700, t['onSecondary'], 'center', 1.5, name='小見出し', ls=1) + 8
    cy += c.text(PAD_X, cy, CW, d.get('title'), 30, 900, t['onSecondary'], 'center', 1.4, head=True, name='メインコピー') + 12
    cy += c.text(PAD_X, cy, CW, d.get('lead'), 14, 400, t['onSecondary'], 'center', 1.8, name='リード文') + 18
    c.image(PAD_X, cy, CW, 220, img_of(b, 'kv'), 'KVメイン画像', name='KVメイン画像', rx=14); cy += 220 + 18
    cy += button(c, PAD_X, cy, CW, 60, d.get('cta')) + 30
    body = c.cut(m)
    c.rect(0, y, W, cy - y, fill=t['secondary'], name='ヒーロー背景')
    c.out += body
    return cy - y


def b_timer(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + 24
    cy += c.text(PAD_X, cy, CW, d.get('title'), 13, 700, t['deep'], 'center', 1.5, name='見出し') + 8
    tw = min(CW, text_w(d.get('lead', ''), 22) + 48)
    c.rect((W - tw) / 2, cy, tw, 52, fill=t['bg'], stroke=t['primary'], sw=1.5, rx=26, name='タイマー枠')
    c.text((W - tw) / 2, cy + 11, tw, d.get('lead'), 22, 700, t['primary'], 'center', 1.35, name='タイマー')
    return cy + 52 + 24 - y


def ribbon_col(c, x, y, w, label, value, note):
    """リボン見出し＋大きな数字の特典1列。高さを返す"""
    t = c.t
    cy = y
    m = c.mark()
    lh = c.text(x + 4, cy + 5, w - 8, label, 11, 700, t['onSecondary'], 'center', 1.4, name='リボンの文言', warn=False)
    txt = c.cut(m)
    c.rect(x, cy, w, lh + 10, fill=t['secondary'], rx=3, name='リボン')
    c.path([('M', x + w / 2 - 5, cy + lh + 10), ('L', x + w / 2, cy + lh + 15), ('L', x + w / 2 + 5, cy + lh + 10), ('Z',)],
           fill=t['secondary'])
    c.out += txt
    cy += lh + 10 + 12
    for k, val in enumerate(str(value or '').split('\n')):   # 改行で特典を複数並べる（2つ目以降は「＋」でつなぐ）
        if k:
            cy += c.text(x, cy, w, '＋', 14, 900, t['primary'], 'center', 1.3, name='プラス', warn=False)
        sp = split_amount(val)
        big = next((z for z in (34, 30, 27, 24) if sp and (text_w(sp[1], z) + text_w(sp[2], 13)) * 1.12 + z * 0.12 <= w),
                   None)                                      # 列の幅に収まる大きさまで数字を下げる
        if big:
            pre, num, post = sp
            if pre:
                cy += c.text(x, cy, w, pre, 12, 700, t['deep'], 'center', 1.4, name='特典の前置き')
            cy += c.runs(x + w / 2, cy, [(num, big, 900, t['deep']), (post, 13, 700, t['deep'])], name='特典の金額')
        else:                                                 # 1行に収まる大きさまで下げる
            fs = 20
            while fs > 13 and text_w(val, fs) > w:
                fs -= 1
            cy += c.text(x, cy + 4, w, val, fs, 900, t['deep'], 'center', 1.35, name='特典の内容') + 4
    if note:
        cy += 4 + c.text(x, cy + 4, w, note, 10, 400, t['mute'], 'center', 1.6, name='特典の条件')
    return cy - y


def b_benefits(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y
    cy += sec_head(c, PAD_X, cy, CW, d.get('title'), d.get('eyebrow') or 'PRESENT')

    def draw(x, yy, w):
        s = yy
        if d.get('lead'):
            yy += c.text(x, yy, w, d['lead'], 14, 700, t['ink'], 'center', 1.6, name='カード見出し') + 14
        cols = [(d.get(f'cap{k}'), d.get(k.lower()), d.get(f'sub{k}')) for k in 'AB' if d.get(k.lower())]
        if len(cols) == 1:                                    # 片側だけ（ゲストページなど）は1列で大きく
            cw_ = min(w, 230)
            return yy + ribbon_col(c, x + (w - cw_) / 2, yy, cw_, *cols[0]) - s
        cw_ = (w - 12) / 2
        hs = [ribbon_col(c, x + i * (cw_ + 12), yy, cw_, *col) for i, col in enumerate(cols)]
        return yy + max(hs or [0]) - s
    cy += card(c, PAD_X, cy, CW, draw, pad=16, name='特典カード') + 14
    if d.get('note'):
        cy += c.text(PAD_X, cy, CW, d['note'], 10.5, 400, t['mute'], 'center', 1.7, name='特典の条件') + 14
    cy += button(c, PAD_X, cy, CW, 60, d.get('cta'))
    return cy + PAD_Y - y


def b_headline(c, b, p, y):
    return PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, b['data'].get('title'), b['data'].get('eyebrow')) - 18 + PAD_Y


def b_text(c, b, p, y):
    d, t = b['data'], c.t
    if b['type'] == 'coupon-message':                             # 紹介者からのメッセージカード
        cy = y + 28

        def draw(x, yy, w):
            s = yy
            yy += c.text(x, yy, w, d.get('title'), 16, 700, t['deep'], 'center', 1.55, head=True, name='見出し')
            if d.get('lead'):
                yy += 8 + para(c, x, yy + 8, w, d.get('lead'), 13.5, 'center')
            return yy - s
        cy += card(c, PAD_X, cy, CW, draw, pad=20, stroke=t['primary'], name='メッセージカード')
        return cy + 28 - y
    cy = y + PAD_Y
    cy += sec_head(c, PAD_X, cy, CW, d.get('title'), d.get('eyebrow'), align=d.get('align', 'center'), size=19)
    h = para(c, PAD_X, cy, CW, d.get('lead'))
    return (cy + h if h else cy - 18) + PAD_Y - y


def b_image(c, b, p, y):
    w, h = slot_size(b, 'img')
    hh = h * CW / w
    c.image(PAD_X, y + 24, CW, hh, img_of(b, 'img'), '画像', name='画像', rx=14)
    return 48 + hh


def b_frame(c, b, p, y):
    d, t = b['data'], c.t

    def draw(x, cy, w):
        s = cy
        cy += c.text(x, cy, w, d.get('title'), 16, 700, t['deep'], 'center', 1.55, head=True, name='見出し') + 10
        cy += para(c, x, cy, w, d.get('lead'), 13.5) + 12
        c.image(x, cy, w, 180, img_of(b, 'img'), 'フレーム内の画像', name='画像')
        return cy + 180 - s
    return PAD_Y + card(c, PAD_X, y + PAD_Y, CW, draw, pad=18, name='フレーム') + PAD_Y


def b_framelist(c, b, p, y):
    """紹介者がすすめるポイント（チェック付きの箇条書き）。画像は支給された項目か showImages のときだけ入れる"""
    d, t = b['data'], c.t; rows = d.get('rows') or []

    def draw(x, cy, w):
        s = cy
        cy += c.text(x, cy, w, d.get('title'), 15, 700, t['deep'], 'center', 1.55,
                     head=True, name='見出し') + 12
        for i, r in enumerate(rows):
            c.open(f'項目{i + 1}')
            check(c, x, cy + 3, 17)
            cy += max(c.text(x + 26, cy, w - 26, r, 14, 500, t['body'], lh=1.7, name='項目の文言'), 22)
            if img_of(b, f'r{i}') or d.get('showImages'):
                c.image(x + 26, cy + 8, w - 26, 140, img_of(b, f'r{i}'), f'画像{i + 1}')
                cy += 148
            cy += 12
            c.close()
        return cy - s - 12
    return PAD_Y + card(c, PAD_X, y + PAD_Y, CW, draw, pad=18, fill=t['point'], stroke='', name='ポイント') + PAD_Y


def b_gallery(c, b, p, y):
    d = b['data']; n = int(d.get('count') or 4)
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or 'GALLERY')
    gw = (CW - 10) / 2
    for i in range(n):
        c.image(PAD_X + (i % 2) * (gw + 10), cy + (i // 2) * (gw + 10), gw, gw, img_of(b, f'g{i}'), f'画像{i + 1}', rx=12)
    cy += ((n + 1) // 2) * (gw + 10) - 10
    return cy + PAD_Y - y


def b_reviewlist(c, b, p, y):
    d, t = b['data'], c.t; rows = d.get('rows') or []
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or 'VOICE')
    for i, r in enumerate(rows):
        def draw(x, yy, w, r=r, i=i):
            c.image(x, yy, 64, 64, img_of(b, f'rv{i}'), '画像', rx=32)
            return max(64, c.text(x + 78, yy + 2, w - 78, r, 13.5, 400, t['body'], lh=1.75, name='口コミ本文'))
        cy += card(c, PAD_X, cy, CW, draw, pad=16, name=f'口コミ{i + 1}') + 12
    bw = 240
    button(c, (W - bw) / 2, cy + 4, bw, 46, d.get('cta'), name='もっと見る', outline=True, pill=True, size=13)
    return cy + 50 + PAD_Y - y


def b_modal(c, b, p, y):
    d, t = b['data'], c.t
    top = y + 24
    m = c.mark()

    def draw(x, yy, w):
        s = yy
        yy += c.text(x, yy, w, d.get('title'), 16, 700, t['ink'], 'center', 1.55, head=True, name='見出し') + 10
        yy += para(c, x, yy, w, d.get('lead'), 13.5) + 16
        bw = min(200, w)
        button(c, x + (w - bw) / 2, yy, bw, 42, d.get('cta'), name='閉じる', outline=True, pill=True, size=13,
               fill=t['mute'], arrow=False)
        return yy + 42 - s
    ch = card(c, PAD_X + 18, top + 30, CW - 36, draw, pad=20, stroke='', name='モーダル')
    body = c.cut(m)
    c.rect(PAD_X, top, CW, ch + 60, fill='#1C1E22', opacity=0.6, rx=14, name='モーダル背景')
    c.out += body
    return ch + 60 + 48


def slider(c, b, y, has_text):
    t = c.t; d = b['data']; slides = slides_of(d)
    iw = CW * 0.78; ix = PAD_X + (CW - iw) / 2
    sw, sh = slot_size(b, 's')
    imh = (iw - 28) * sh / sw

    def draw(x, yy, w):
        s0 = slides[0]; s = yy
        c.image(x, yy, w, imh, img_of(b, 's0'), 'スライド1 画像', name='スライド画像'); yy += imh
        if has_text and s0.get('text'):
            yy += 12 + c.text(x, yy + 12, w, s0['text'], 13, 400, t['body'], lh=1.75, name='スライド説明文')
        if s0.get('btn'):
            yy += 12 + button(c, x, yy + 12, w, 44, s0['btn'], name='スライドボタン', size=13)
        return yy - s
    m = c.mark()
    h = card(c, ix, y, iw, draw, pad=14, name='スライド1')
    body = c.cut(m)
    if len(slides) > 1:                                          # 前後スライドのチラ見せ
        c.rect(ix + iw + 10, y + 16, 40, h - 32, fill=t['bg'], stroke=t['line'], rx=14, name='次のスライド（チラ見せ）')
        c.rect(ix - 50, y + 16, 40, h - 32, fill=t['bg'], stroke=t['line'], rx=14, name='前のスライド（チラ見せ）')
    c.out += body
    cy = y + h + 16
    c.open('ページ送り')
    n = len(slides)
    x0 = (W - (24 + (n - 1) * 16)) / 2
    for i in range(n):
        if i == 0:
            c.rect(x0, cy, 24, 8, fill=t['primary'], rx=4); x0 += 32
        else:
            c.circle(x0 + 4, cy + 4, 4, fill=t['line']); x0 += 16
    c.close()
    return cy + 8 - y


def b_slider(c, b, p, y):
    d = b['data']; cy = y + PAD_Y
    if b['type'] != 'image-slider':
        cy += sec_head(c, PAD_X, cy, CW, d.get('title'), d.get('eyebrow') or ('HINT' if b['type'] == 'hint' else None))
    cy += slider(c, b, cy, b['type'] != 'image-slider')
    return cy + PAD_Y - y


def b_flow(c, b, p, y):
    d, t = b['data'], c.t; steps = d.get('steps') or []
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or 'FLOW')
    show = d.get('showImages', True)
    for i, s in enumerate(steps):
        def draw(x, yy, w, s=s, i=i):
            st = yy
            c.text(x, yy, 80, f'STEP {i + 1}', 10.5, 700, t['primary'], lh=1.4, name='ステップ番号', ls=1)
            yy += 18
            yy += c.text(x, yy, w, s, 15, 700, t['ink'], lh=1.6, name='ステップ説明')
            if show:
                c.image(x, yy + 12, w, 110, img_of(b, f'st{i}'), f'STEP{i + 1} 画像')
                yy += 122
            return yy - st
        cy += card(c, PAD_X, cy, CW, draw, pad=18, name=f'STEP{i + 1}')
        if i < len(steps) - 1:
            c.path([('M', W / 2 - 8, cy + 6), ('L', W / 2, cy + 13), ('L', W / 2 + 8, cy + 6)], stroke=t['primary'],
                   sw=2, name='つなぎ矢印')
            cy += 20
    return cy + PAD_Y - y


def b_flowtab(c, b, p, y):
    d, t = b['data'], c.t; steps = d.get('steps') or []
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or 'FLOW')
    c.open('タブ')
    c.rect(PAD_X, cy, CW, 44, fill=t['field'], rx=22)
    c.rect(PAD_X + 4, cy + 4, CW / 2 - 4, 36, fill=t['primary'], rx=18)
    c.text(PAD_X, cy + 12, CW / 2, d.get('t1'), 13, 700, t['onPrimary'], 'center', 1.5)
    c.text(PAD_X + CW / 2, cy + 12, CW / 2, d.get('t2'), 13, 700, t['mute'], 'center', 1.5)
    c.close()
    cy += 60
    for i, s in enumerate(steps):
        c.open(f'STEP{i + 1}')
        if i < len(steps) - 1:
            c.line(PAD_X + 15, cy + 30, PAD_X + 15, cy + 62, t['line'], 2)
        num_badge(c, PAD_X + 15, cy + 15, i + 1)
        hh = c.text(PAD_X + 42, cy + 3, CW - 42, s, 14, 500, t['body'], lh=1.7, name='ステップ説明')
        cy += max(64, hh + 20)
        c.close()
    return cy - 20 + PAD_Y - y


def b_accordion(c, b, p, y):
    d, t = b['data'], c.t; faq = b['type'] == 'faq'
    items = [it if isinstance(it, dict) else {'q': str(it), 'a': ''} for it in d.get('items') or []]
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or ('FAQ' if faq else None))
    for i, it in enumerate(items):
        def draw(x, yy, w, it=it):
            s = yy
            ind = 30 if faq else 0
            if faq:
                c.circle(x + 11, yy + 11, 11, fill=t['primary'])
                c.text(x, yy + 3, 22, 'Q', 12, 700, t['onPrimary'], 'center', 1.4, warn=False)
            hh = c.text(x + ind, yy + 1, w - ind - 22, it.get('q'), 14, 700, t['ink'], lh=1.55,
                        name='質問' if faq else '項目見出し')
            cxp = x + w - 7
            c.path([('M', cxp - 5, yy + 8), ('L', cxp, yy + 13), ('L', cxp + 5, yy + 8)], stroke=t['mute'], sw=1.6,
                   name='開閉')
            yy += max(hh, 22)
            if it.get('a'):
                c.line(x, yy + 10, x + w, yy + 10, t['line'], 1)
                yy += 20
                if faq:
                    c.text(x, yy, 22, 'A', 13, 700, t['primary'], 'center', 1.75, warn=False)
                yy += c.text(x + ind, yy, w - ind, it['a'], 13, 400, t['body'], lh=1.75,
                             name='回答' if faq else '開いた中身')
            return yy - s
        cy += card(c, PAD_X, cy, CW, draw, pad=16, name=f'項目{i + 1}') + 10
    return cy - 10 + PAD_Y - y


def b_video(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or 'MOVIE')
    h = CW * 9 / 16
    c.image(PAD_X, cy, CW, h, img_of(b, 'thumb'), ' ', name='動画サムネイル', rx=14)
    c.open('再生ボタン')
    c.circle(W / 2, cy + h / 2, 26, fill='#FFFFFF', opacity=0.92)
    cx, cc = W / 2 + 2, cy + h / 2
    c.path([('M', cx - 7, cc - 10), ('L', cx + 10, cc), ('L', cx - 7, cc + 10), ('Z',)], fill=t['primary'])
    c.close()
    return cy + h + PAD_Y - y


def field(c, x, y, w, label, h=50, name='入力欄', content=None):
    t = c.t
    c.open(name)
    lh = c.text(x, y, w - 50, label, 13.5, 700, t['ink'], lh=1.5, name='項目名')
    lw = min(w - 50, text_w(label or '', 13.5))
    c.rect(x + lw + 8, y + 2.5, 32, 16, fill=REQ_RED, rx=8, name='必須')
    c.text(x + lw + 8, y + 2.5, 32, '必須', 9.5, 700, '#FFFFFF', 'center', 1.7, warn=False)
    y += lh + 8
    m = c.mark()
    ch = c.text(x + 14, y + 12, w - 28, content, 13.5, 400, t['body'], lh=1.8, name='初期メッセージ') if content else 0
    body = c.cut(m)
    h = max(h, ch + 24)
    c.rect(x, y, w, h, fill=t['field'], stroke=t['line'], rx=8, name='入力枠')
    c.out += body
    c.close()
    return lh + 8 + h


def b_inviteform(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or 'SHARE')

    def draw(x, yy, w):
        s = yy
        for f in ('f1', 'f2'):
            yy += field(c, x, yy, w, d.get(f), name=d.get(f) or f) + 16
        yy += field(c, x, yy, w, d.get('f3'), h=120, name='メッセージ欄', content=d.get('msg'))
        yy += 6 + c.text(x, yy + 6, w, 'このメッセージが紹介URLと一緒に届きます', 10.5, 400, t['mute'], lh=1.6,
                         name='注記') + 18
        # 個人情報の同意
        c.open('個人情報について')
        lh = c.text(x, yy, w - 50, '個人情報について', 13.5, 700, t['ink'], lh=1.5, name='項目名')
        c.rect(x + text_w('個人情報について', 13.5) + 8, yy + 2.5, 32, 16, fill=REQ_RED, rx=8, name='必須')
        c.text(x + text_w('個人情報について', 13.5) + 8, yy + 2.5, 32, '必須', 9.5, 700, '#FFFFFF', 'center', 1.7, warn=False)
        yy += lh + 6
        yy += c.text(x, yy, w, d.get('privacy'), 12, 400, t['body'], lh=1.7, name='個人情報の説明') + 10
        c.rect(x, yy + 1, 18, 18, fill=t['bg'], stroke=t['mute'], sw=1.2, rx=3, name='チェックボックス')
        c.text(x + 26, yy, w - 26, '同意する', 13.5, 400, t['body'], lh=1.5, name='同意する')
        c.close()
        yy += 22 + 26
        # 紹介方法：LINE → メール → リンク を縦に並べる（ページ上部の CTA と同じ大きさ・形）
        yy += c.text(x, yy, w, d.get('methodTitle') or '紹介方法選択', 16, 700, t['ink'], 'center', 1.5, name='紹介方法の見出し') + 12
        yy += button(c, x, yy, w, 60, d.get('cta'), name='LINEで送る') + 12
        yy += button(c, x, yy, w, 60, d.get('mailCta') or 'メールで送る', name='メールで送る', fill=t['mail'], ico='mail')
        if d.get('mailNote'):
            yy += 6 + c.text(x, yy + 6, w, d['mailNote'], 10.5, 400, t['mute'], lh=1.6, name='メールの注記')
        yy += 22
        if d.get('snsLead'):
            yy += c.text(x, yy, w, d['snsLead'], 15, 700, t['ink'], 'center', 1.55, name='SNSシェアの見出し') + 12
        yy += button(c, x, yy, w, 60, d.get('linkCta') or 'リンクでシェア', name='リンクでシェア', fill=t['link'], ico='link')
        return yy - s
    cy += card(c, PAD_X, cy, CW, draw, pad=18, name='紹介フォーム')
    return cy + PAD_Y - y


def b_guestform(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or 'ENTRY')

    def draw(x, yy, w):
        s = yy
        for f in ('f1', 'f2'):
            yy += field(c, x, yy, w, d.get(f), name=d.get(f) or f) + 16
        yy += 4 + button(c, x, yy + 4, w, 60, d.get('cta'))
        return yy - s
    cy += card(c, PAD_X, cy, CW, draw, pad=18, name='ゲストフォーム')
    return cy + PAD_Y - y


def b_code(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y + sec_head(c, PAD_X, y + PAD_Y, CW, d.get('title'), d.get('eyebrow') or 'COUPON')

    def draw(x, yy, w):
        s = yy
        yy += c.text(x, yy, w, d.get('lead') or 'ご予約時にこのコードをお伝えください', 12.5, 400, t['mute'], 'center',
                     1.6, name='説明') + 12
        c.rect(x, yy, w, 64, fill=t['tint'], stroke=t['primary'], sw=1.5, rx=10, dash=4, name='コード枠')
        c.text(x, yy + 15, w, d.get('code'), 24, 900, t['deep'], 'center', 1.4, name='コード', ls=2)
        yy += 78
        bw = min(w, 220)
        yy += button(c, x + (w - bw) / 2, yy, bw, 44, d.get('cta'), name='コピーボタン', outline=True, pill=True,
                     size=13, arrow=False)
        return yy - s
    cy += card(c, PAD_X, cy, CW, draw, pad=18, name='クーポンカード')
    return cy + PAD_Y - y


def b_cta(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y
    cy += c.text(PAD_X, cy, CW, d.get('title'), 17, 700, t['ink'], 'center', 1.55, head=True, name='見出し') + 14
    cy += button(c, PAD_X, cy, CW, 60, d.get('cta'))
    if d.get('fine'):
        cy += 8 + c.text(PAD_X, cy + 8, CW, d['fine'], 10.5, 400, t['mute'], 'center', 1.6, name='注記')
    return cy + PAD_Y - y


def b_button(c, b, p, y):
    return 24 + button(c, PAD_X, y + 24, CW, 60, b['data'].get('label')) + 24


def b_terms(c, b, p, y):
    d, t = b['data'], c.t; warn = b['type'] == 'notice-list'
    cy = y + 28

    def draw(x, yy, w):
        s = yy
        c.circle(x + 9, yy + 10, 9, fill=t['ink'])
        c.text(x, yy + 3, 18, '!' if warn else 'i', 11, 700, '#FFFFFF', 'center', 1.3, warn=False)
        yy += c.text(x + 26, yy, w - 26, d.get('title'), 14.5, 700, t['ink'], lh=1.4, name='見出し') + 10
        for i, s_ in enumerate(d.get('bullets') or []):
            c.circle(x + 4, yy + 12 * 1.8 / 2, 2.2, fill=t['ink'])
            yy += c.text(x + 14, yy, w - 14, s_, 12, 400, t['body'], lh=1.8, name=f'項目{i + 1}') + 4
        return yy - s - 4
    m = c.mark()                                          # 背景なし：アイコン＋見出し＋箇条書きだけ
    cy += draw(PAD_X, cy, CW)
    body = c.cut(m)
    c.open('規約'); c.out += body; c.close()
    return cy + 28 - y


def b_footer(c, b, p, y):
    """invy 標準のフッター：規約リンクを枠で区切って並べ、下に黒帯のコピーライト"""
    d, t = b['data'], c.t
    links = [s for s in (d.get('a'), d.get('b')) if s]
    h1 = 48
    c.open('規約リンク')
    c.line(0, y + 0.5, W, y + 0.5, t['line'], 1)
    cw_ = W / max(1, len(links))
    for k, s in enumerate(links):
        if k:
            c.line(cw_ * k, y, cw_ * k, y + h1, t['line'], 1)
        c.text(cw_ * k, y + (h1 - 12 * 1.6) / 2, cw_, s, 12, 400, t['ink'], 'center', 1.6, name='リンク', maxlines=1)
    c.close()
    c.rect(0, y + h1, W, 28, fill=t['footer'], name='コピーライト帯')
    c.text(0, y + h1 + 6, W, d.get('copyright') or 'Copyright © 2026 INVY All Rights Reserved.', 9.5, 700,
           '#FFFFFF', 'center', 1.6, name='コピーライト', maxlines=1)
    return h1 + 28


def b_floating(c, b, p, y):
    t = c.t
    c.line(0, y, W, y, t['line'], 1)
    button(c, PAD_X, y + 10, CW, 56, b['data'].get('cta'), name='バナー', pill=True, size=15)
    return 76


SHAPES = {
  'brand-logo': b_header, 'kv-image': b_kvimg, 'keyvisual': b_kv, 'service-show-timer': b_timer,
  'benefits': b_benefits, 'headline': b_headline, 'text-editor': b_text, 'image': b_image, 'frame': b_frame,
  'frame-list': b_framelist, 'review-gallery': b_gallery, 'review-list': b_reviewlist,
  'image-slider': b_slider, 'image-slider-text': b_slider, 'hint': b_slider,
  'coupon-message': b_text, 'service-introduction': b_text, 'service-show-recommend': b_text,
  'flow': b_flow, 'flow-tab': b_flowtab, 'invitation-detail': b_accordion, 'faq': b_accordion,
  'accordion-list': b_accordion, 'youtube': b_video, 'modal': b_modal, 'button': b_button,
  'invite-form': b_inviteform, 'guest-form': b_guestform, 'invitation-code': b_code,
  'client-site-link': b_cta, 'coming-form-link': b_cta, 'please-read': b_terms, 'notice-list': b_terms,
  'footer': b_footer, 'invitation-banner': b_floating,
}
# 交互背景（白／淡色）の対象にしないブロック
EDGE = {'brand-logo', 'kv-image', 'keyvisual', 'footer', 'invitation-banner', 'please-read', 'notice-list',
        'coupon-message', 'service-show-timer', 'button'}


def render_page(page, spec, scale=3, base_dir='.'):
    """1ページを描画。(要素リスト, 幅pt, 高さpt, 警告, ブロックごとの (y, h)) を返す"""
    theme = theme_of(spec)
    c = Canvas(scale, theme, base_dir)
    page = dict(page, _project=spec.get('project', ''))
    y = 0; spans = []; alt = False
    for i, b in enumerate(page['blocks']):
        st = b.get('style') or {}
        c.t = dict(theme)
        if st.get('textColor'):
            c.t.update(ink=st['textColor'], body=st['textColor'])
        bg = st.get('bg')
        if not bg:
            if b['type'] in EDGE:
                bg = theme['bg']
            else:
                bg = theme['soft'] if alt else theme['bg']
                alt = not alt
        c.open(f"{i + 1:02d}_{BLOCKS[b['type']]['label']}")
        m = c.mark()
        h = SHAPES[b['type']](c, b, page, y)
        if b.get('minH') and b['minH'] > h:
            h = b['minH']
        body = c.cut(m)
        op = st.get('bgOpacity')
        c.rect(0, y, W, h, fill=bg, name='背景', opacity=None if op in (None, 100) else op / 100)
        c.out += body
        if st.get('border'):
            c.rect(0.5, y + 0.5, W - 1, h - 1, stroke=st.get('borderColor') or theme['line'], sw=1, name='枠線')
        c.close()
        spans.append((y, h))
        y += h
    c.t = theme
    return c.out, W, y, c.warn, spans


# ---------------------------------------------------------------- OGP 画像・LINE 表示イメージ
def page_of(spec, pt):
    return next((p for p in spec.get('pages', []) if p.get('pageType') == pt), None)


def kv_data(spec):
    for pt in ('inviter', 'guest'):
        for b in (page_of(spec, pt) or {}).get('blocks', []):
            if b['type'] == 'kv-image':
                return b['data']
    return {}


def offers(spec):
    for pt in ('guest', 'inviter'):              # OGP を見るのはシェアを受け取る側なので、ゲストページの特典を優先
        for b in (page_of(spec, pt) or {}).get('blocks', []):
            if b['type'] == 'benefits':
                return b['data']
    o = spec.get('offer') or {}
    return {'capA': 'ご紹介くださった方', 'a': o.get('inviter', ''), 'capB': 'ご紹介を受けた方', 'b': o.get('guest', '')}


def draw_ogp(c, x0, y0, spec, u=1.0):
    """OGP 画像を描く。基準は 400×210pt（scale=3 で 1200×630px）。u は縮尺"""
    t = c.t
    Wd, Hd = 400 * u, 210 * u
    kv, of = kv_data(spec), offers(spec)
    c.open('OGP画像')
    c.rect(x0, y0, Wd, Hd, fill=t['secondary'], name='OGP背景')
    c.rect(x0, y0 + Hd - 10 * u, Wd, 10 * u, fill=t['cream'], name='帯')
    c.text(x0 + 22 * u, y0 + 20 * u, 210 * u, spec.get('project', ''), 11 * u, 900, t['onSecondary'], lh=1.4,
           name='ロゴ（画像に差し替え）', maxlines=1, warn=False)
    yy = y0 + 50 * u
    if kv.get('sub'):
        yy += c.text(x0 + 22 * u, yy, 220 * u, kv['sub'], 9.5 * u, 700, t['onSecondary'], lh=1.5, name='小見出し',
                     maxlines=1, warn=False) + 4 * u
    c.text(x0 + 22 * u, yy, 216 * u, kv.get('copy') or spec.get('project', ''), 21 * u, 900, t['onSecondary'],
           lh=1.38, head=True, name='メインコピー', maxlines=3, warn=False)
    cx, cy, cw, ch = x0 + 252 * u, y0 + 26 * u, 128 * u, 158 * u        # 右側の特典カード（シェアを受け取る側の特典）
    c.rect(cx, cy, cw, ch, fill='#FFFFFF', rx=12 * u, name='特典カード')
    cap = of.get('capB') or of.get('capA') or '紹介特典'
    vals = [v for v in str(of.get('b') or of.get('a') or '').split('\n') if v][:2]
    c.rect(cx + 10 * u, cy + 14 * u, cw - 20 * u, 16 * u, fill=t['secondary'], rx=2 * u, name='リボン')
    c.text(cx + 10 * u, cy + 15.5 * u, cw - 20 * u, cap, 8 * u, 700, t['onSecondary'], 'center', 1.6, maxlines=1, warn=False)
    blocks = []
    for v in vals:
        sp = split_amount(v)
        blocks.append(sp if sp and text_w(sp[1], 22 * u) + text_w(sp[2], 8.5 * u) < cw - 14 * u else None)
    each = 44 * u if len(vals) > 1 else 60 * u
    yy = cy + 38 * u + (ch - 38 * u - each * len(vals) - (12 * u if len(vals) > 1 else 0)) / 2
    for k, (v, sp) in enumerate(zip(vals, blocks)):
        if k:
            c.text(cx, yy - 2 * u, cw, '＋', 10 * u, 900, t['primary'], 'center', 1.2, warn=False)
            yy += 12 * u
        if sp:
            if sp[0]:
                c.text(cx + 6 * u, yy, cw - 12 * u, sp[0], 8 * u, 700, t['deep'], 'center', 1.4, maxlines=1, warn=False)
            c.runs(cx + cw / 2, yy + 13 * u, [(sp[1], 22 * u, 900, t['deep']), (sp[2], 8.5 * u, 700, t['deep'])])
        else:
            c.text(cx + 6 * u, yy + 8 * u, cw - 12 * u, v, 11 * u, 900, t['deep'], 'center', 1.35, maxlines=2, warn=False)
        yy += each
    c.close()
    return Wd, Hd


def ogp_file(spec, base_dir):
    ps = (page_of(spec, 'guest') or page_of(spec, 'inviter') or {}).get('settings') or {}
    f = ps.get('ogp')
    return f if f and os.path.exists(os.path.join(base_dir, f)) else None


def render_ogp(spec, scale=3, base_dir='.'):
    c = Canvas(scale, theme_of(spec), base_dir)
    f = ogp_file(spec, base_dir)
    if f:
        c.image(0, 0, 400, 210, f, 'OGP画像', name='OGP画像')
        return c.out, 400, 210, c.warn
    w, h = draw_ogp(c, 0, 0, spec)
    return c.out, w, h, c.warn


def render_line(spec, scale=3, base_dir='.'):
    """紹介者が LINE で送ったとき、受け取った側のトーク画面での見え方（イメージ。実際の見え方は端末で変わる）"""
    c = Canvas(scale, theme_of(spec), base_dir)
    inv = page_of(spec, 'inviter') or {}
    gst = page_of(spec, 'guest') or inv
    msg = next((b['data'].get('msg') for b in inv.get('blocks', []) if b['type'] == 'invite-form'), '') or ''
    ps = gst.get('settings') or {}
    title = ps.get('title') or gst.get('title') or spec.get('project', '')
    desc = ps.get('description') or ''
    slug = spec.get('slug') or 'client'
    c.rect(0, 0, W, 10, fill='#8CABD9', name='トーク背景')         # 高さは最後に差し替える
    bg_i = len(c.out) - 1
    c.open('トークのヘッダー')
    c.rect(0, 0, W, 48, fill='#F7F8FA')
    c.path([('M', 22, 17), ('L', 15, 24), ('L', 22, 31)], stroke='#1C1E22', sw=2)
    c.text(40, 14, 200, 'お友だち', 15, 700, '#1C1E22', lh=1.4, warn=False)
    c.close()
    y = 68
    c.circle(30, y + 16, 16, fill='#DDE3EA', name='アイコン')
    bx, bw = 56, 260
    c.open('メッセージ')
    m = c.mark()
    th = c.text(bx + 14, y + 12, bw - 28, msg, 13.5, 400, '#1C1E22', lh=1.65, name='メッセージ本文', warn=False)
    th += c.text(bx + 14, y + 12 + th + (4 if th else 0), bw - 28, f'https://invy.jp/{slug}/guest?code=…', 12, 400,
                 '#2B6BD6', lh=1.6, name='紹介URL', warn=False) + (4 if th else 0)
    body = c.cut(m)
    c.rect(bx, y, bw, th + 24, fill='#FFFFFF', rx=16, name='吹き出し')
    c.out += body
    c.close()
    y += th + 24 + 10
    c.open('リンクプレビュー')
    u = bw / 400
    ogh = 210 * u
    m = c.mark()
    f = ogp_file(spec, c.base)
    if f:
        c.image(bx, y, bw, ogh, f, 'OGP画像')
    else:
        draw_ogp(c, bx, y, spec, u)
    ty = y + ogh + 10
    ty += c.text(bx + 12, ty, bw - 24, title, 13, 700, '#1C1E22', lh=1.5, name='タイトル', maxlines=2, warn=False)
    if desc:
        ty += 2 + c.text(bx + 12, ty + 2, bw - 24, desc, 11, 400, '#767C83', lh=1.6, name='説明文', maxlines=2, warn=False)
    ty += 4 + c.text(bx + 12, ty + 4, bw - 24, 'invy.jp', 10, 400, '#9AA0A6', lh=1.6, name='ドメイン', warn=False)
    body = c.cut(m)
    c.rect(bx, y, bw, ty + 10 - y, fill='#FFFFFF', rx=16, name='カード')
    c.out += body
    c.close()
    y = ty + 10
    c.text(bx + bw + 6, y - 16, 40, '12:34', 9.5, 400, '#FFFFFF', lh=1.5, warn=False)
    H = max(560, y + 60)
    c.out[bg_i] = c.out[bg_i].replace(f'height="{c.n(10)}"', f'height="{c.n(H)}"')
    return c.out, W, H, c.warn


def svg_doc(groups, width_pt, height_pt, scale):
    w, h = round(width_pt * scale), round(height_pt * scale)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n' + '\n'.join(groups) + '\n</svg>\n')
