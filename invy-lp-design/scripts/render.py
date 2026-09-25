"""spec.json のページを SVG に描画するレイアウトエンジン。

- ブラウザ不要（標準ライブラリのみ）。プレビューも Figma 書き出しも同じ SVG を使うので、見た目が食い違わない
- 座標はすべて実機 375pt 幅の pt。出力時に scale を掛ける（既定 3 → 1125px）
- 数値は invy 実機 CSS に合わせる（本文14 / 見出し24 / CTA高さ69 / 左右余白20）。ここを崩さない
- テキストは行ごとに改行位置を確定させて出す（Figma 側でフォント差による折り返しズレが起きない）
"""
import base64, mimetypes, os, re
from catalog import BLOCKS, image_slots

W = 375            # 実機幅（pt）
PAD_X = 20         # 左右余白
PAD_Y = 32         # ブロック上下余白
CW = W - PAD_X * 2  # 335

WIRE = dict(primary='#332C2B', onPrimary='#FFFFFF', ink='#1B1717', body='#332C2B', sub='#8C817D',
            line='#E2D9D5', soft='#F5F2EF', ph='#EDE8E5', phLine='#D2C9C5', accent='#B8443F',
            bg='#FFFFFF', footer='#2A2423', onFooter='#CFC6C2', radius=2, pill=999,
            font='Noto Sans JP', headFont='Zen Kaku Gothic New')
LINE_GREEN = '#1BB71F'   # invy 紹介フォームの LINE ボタン色（CMS 固定）
REQ_RED = '#C0392B'


def theme_of(spec):
    t = dict(WIRE)
    th = spec.get('theme') or {}
    if th.get('mode') == 'brand':
        for k in WIRE:
            if k in th:
                t[k] = th[k]
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
            return size * 0.56
        if ch.isupper():
            return size * 0.64
        return size * 0.53
    if 0xFF61 <= o <= 0xFF9F:
        return size * 0.5
    return size * 1.0


def text_w(s, size, ls=0):
    return sum(char_w(c, size) + ls for c in s)


def wrap(text, size, maxw, ls=0):
    lines = []
    for para in str(text or '').split('\n'):
        line = ''
        for tok in TOKEN.findall(para):
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
        return str(int(v)) if abs(v - round(v)) < 1e-6 else f'{v:.1f}'

    def uid(self, name):
        if not name:
            return ''
        k = self.ids.get(name, 0) + 1; self.ids[name] = k
        return f' id="{xesc(name if k == 1 else f"{name}-{k}")}"'

    def open(self, name):
        self.out.append(f'<g{self.uid(name)}>')

    def close(self):
        self.out.append('</g>')

    def rect(self, x, y, w, h, fill=None, stroke=None, sw=1, rx=0, name=None, opacity=None):
        a = f'<rect{self.uid(name)} x="{self.n(x)}" y="{self.n(y)}" width="{self.n(w)}" height="{self.n(h)}"'
        if rx:
            a += f' rx="{self.n(min(rx, h / 2, w / 2))}"'
        a += f' fill="{fill or "none"}"'
        if opacity is not None:
            a += f' fill-opacity="{opacity}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{self.n(sw)}"'
        self.out.append(a + '/>')

    def line(self, x1, y1, x2, y2, stroke, sw=1):
        self.out.append(f'<line x1="{self.n(x1)}" y1="{self.n(y1)}" x2="{self.n(x2)}" y2="{self.n(y2)}" '
                        f'stroke="{stroke}" stroke-width="{self.n(sw)}"/>')

    def circle(self, cx, cy, r, fill=None, stroke=None, sw=1):
        a = f'<circle cx="{self.n(cx)}" cy="{self.n(cy)}" r="{self.n(r)}" fill="{fill or "none"}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{self.n(sw)}"'
        self.out.append(a + '/>')

    def text(self, x, y, w, s, size=14, weight=400, color=None, align='left', lh=1.75, head=False,
             name=None, ls=0, maxlines=None):
        """折り返して描画し、使った高さ（pt）を返す。空文字なら 0。"""
        if s is None or str(s).strip() == '':
            return 0
        lines = wrap(s, size, w, ls)
        if maxlines and len(lines) > maxlines:
            lines = lines[:maxlines]; lines[-1] = lines[-1][:-1] + '…'
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

    def image(self, x, y, w, h, src, label, name=None, fit='cover'):
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
        self.rect(x, y, w, h, fill=t['ph'], stroke=t['phLine'], sw=1)
        self.line(x, y, x + w, y + h, t['phLine'], 0.7)
        self.line(x, y + h, x + w, y, t['phLine'], 0.7)
        if w >= 60 and h >= 24:
            fs = 12 if w >= 140 else 9
            lw = min(w - 12, text_w(label, fs) + 18)
            self.rect(x + (w - lw) / 2, y + h / 2 - fs, lw, fs * 2, fill=t['soft'], stroke=t['phLine'], sw=0.7, rx=3)
            self.text(x + (w - lw) / 2, y + h / 2 - fs, lw, label, fs, 400, WIRE['sub'], 'center', lh=2, maxlines=1)
        self.close()


# ---------------------------------------------------------------- 部品
def img_of(b, slot):
    return (b.get('images') or {}).get(slot)


def slot_size(b, slot_prefix):
    for s, _, w, h in BLOCKS[b['type']].get('images', []):
        if s.replace('{i}', '') == slot_prefix:
            return w, h
    return CW, 200


def button(c, x, y, w, h, label, name='ボタン', fill=None, color=None, size=None, outline=False, pill=False):
    t = c.t
    rx = h / 2 if pill else t['radius']
    if outline:
        c.rect(x, y, w, h, fill=t['bg'], stroke=fill or t['primary'], sw=2 if not pill else 1, rx=rx, name=name + '_背景')
    else:
        c.rect(x, y, w, h, fill=fill or t['primary'], rx=rx, name=name + '_背景')
    fs = size or max(10, round(h * 0.26))
    c.text(x + 8, y + (h - fs * 1.4) / 2, w - 16, label, fs, 500, color or (t['primary'] if outline else t['onPrimary']),
           'center', lh=1.4, name=name + '_文言', maxlines=1)
    return h


def heading(c, x, y, w, s, size=24, align='left', mb=16, name='見出し', weight=500):
    h = c.text(x, y, w, s, size, weight, c.t['ink'], align, lh=1.5 if size >= 20 else 1.6, head=True, name=name)
    return h + (mb if h else 0)


def paragraph(c, x, y, w, s, size=14, mb=10, align='left', name='本文', color=None):
    h = c.text(x, y, w, s, size, 400, color or c.t['body'], align, lh=1.75, name=name)
    return h + (mb if h else 0)


def slides_of(d):
    out = []
    for s in d.get('slides') or []:
        out.append(s if isinstance(s, dict) else {'text': str(s)})
    return out or [{'text': ''}]


# ---------------------------------------------------------------- ブロック描画
# 各関数は (canvas, block, page, y) を受け取り、ブロックの高さ（pt）を返す

def b_header(c, b, p, y):
    """CMS の設定：ロゴ表示位置（左寄せ/中央）、紹介CTA（あり/なし）、バナー種類（テキスト/画像）、ボタンスタイル（角丸/四角）"""
    t, d = c.t, b['data']
    h = 50
    c.line(0, y + h - 0.5, W, y + h - 0.5, t['ph'], 1)
    center = d.get('logoPos') == 'center'
    has_cta = d.get('ctaOn', True) not in (False, 'off', 'なし')
    lx = (W - 140) / 2 if center or not has_cta else 12
    c.image(lx, y + 8, 140, 34, img_of(b, 'logo'), 'ロゴ', name='ロゴ', fit='contain')
    if not has_cta:
        return h
    if d.get('ctaType') == 'image':
        c.image(W - 126, y + 7, 116, 36, img_of(b, 'ctaImg'), 'ボタン画像', name='ヘッダーボタン画像', fit='contain')
    elif d.get('btnShape') == 'round':
        button(c, W - 128, y + 8, 118, 34, d.get('cta'), name='ヘッダーボタン', pill=True, size=11)
    else:
        c.rect(W - 120, y, 120, h - 1, fill=t['primary'], name='ヘッダーボタン_背景')
        c.text(W - 116, y + (h - 1 - 14 * 1.4) / 2, 112, d.get('cta'), 14, 500, t['onPrimary'], 'center', 1.4,
               name='ヘッダーボタン_文言', maxlines=1)
    return h


def b_kvimg(c, b, p, y):
    c.image(0, y, W, 500, img_of(b, 'kv'), 'KV画像 375×500pt', name='KV画像')
    return 500


def b_kv(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y
    cy += paragraph(c, PAD_X, cy, CW, d.get('eyebrow'), 12, 8, 'center', '小見出し', t['sub'])
    h = c.text(PAD_X, cy, CW, d.get('title'), 32, 900, t['ink'], 'center', 1.35, head=True, name='メインコピー')
    cy += h + (12 if h else 0)
    cy += paragraph(c, PAD_X, cy, CW, d.get('lead'), 16, 16, 'center', 'リード文')
    c.image(PAD_X, cy, CW, 250, img_of(b, 'kv'), 'KVメイン画像', name='KVメイン画像'); cy += 250 + 16
    cy += button(c, PAD_X, cy, CW, 69, d.get('cta'))
    return cy + PAD_Y - y


def b_timer(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y
    cy += heading(c, PAD_X, cy, CW, d.get('title'), 18, 'center', 10)
    tw = min(CW, text_w(d.get('lead', ''), 20) + 40)
    c.rect((W - tw) / 2, cy, tw, 52, fill='#F7F4F2', stroke=t['line'], name='タイマー枠')
    c.text((W - tw) / 2, cy + 10, tw, d.get('lead'), 20, 500, t['ink'], 'center', 1.6, name='タイマー')
    return cy + 52 + PAD_Y - y


def b_benefits(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y
    x0, w0 = PAD_X, CW
    top = cy
    cy += 20
    body = []  # カードは中身の高さが決まってから描くため、先に中身を別バッファへ
    mark = len(c.out)
    cy += heading(c, x0 + 16, cy, w0 - 32, d.get('title'), 24, 'center', 12)
    for ico, cap, val in (('ico1', d.get('capA'), d.get('a')), ('ico2', d.get('capB'), d.get('b'))):
        c.image(x0 + 16, cy, 50, 50, img_of(b, ico), 'アイコン', name='特典アイコン', fit='contain')
        tx = x0 + 16 + 50 + 12
        hh = c.text(tx, cy, w0 - 32 - 62, cap, 11, 400, t['sub'], lh=1.6, name='特典ラベル')
        hv = c.text(tx, cy + hh + 3, w0 - 32 - 62, val, 18, 700, t['ink'], lh=1.4, head=True, name='特典内容')
        cy += max(50, hh + 3 + hv) + 12
    if d.get('note'):
        cy += paragraph(c, x0 + 16, cy, w0 - 32, d.get('note'), 11, 4, name='特典の条件', color=t['sub'])
    cy += 8
    body = c.out[mark:]; del c.out[mark:]
    c.rect(x0, top, w0, cy - top, fill=t['bg'], stroke=t['line'], name='特典カード')
    c.out += body
    cy += 16
    cy += button(c, PAD_X, cy, CW, 69, d.get('cta'))
    return cy + PAD_Y - y


def b_headline(c, b, p, y):
    return PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, b['data'].get('title'), 24, mb=0) + PAD_Y


def b_text(c, b, p, y):
    d = b['data']; cy = y + PAD_Y
    cy += heading(c, PAD_X, cy, CW, d.get('title'), 18, mb=10)
    cy += paragraph(c, PAD_X, cy, CW, d.get('lead'), mb=0)
    return max(cy - y, PAD_Y) + PAD_Y


def b_image(c, b, p, y):
    w, h = slot_size(b, 'img')
    c.image(PAD_X, y + PAD_Y, CW, h * CW / w, img_of(b, 'img'), '画像', name='画像')
    return PAD_Y * 2 + h * CW / w


def framed(c, y, draw, pad=(16, 12)):
    """枠付きカードの中身を描いてから枠を敷く。draw(x, y, w) -> 高さ"""
    mark = len(c.out)
    x, w = PAD_X + pad[1], CW - pad[1] * 2
    h = draw(x, y + pad[0], w) + pad[0] * 2
    body = c.out[mark:]; del c.out[mark:]
    c.rect(PAD_X, y, CW, h, fill=c.t['bg'], stroke='#D8CFCB', name='フレーム')
    c.out += body
    return h


def b_frame(c, b, p, y):
    d = b['data']

    def draw(x, cy, w):
        s = cy
        cy += heading(c, x, cy, w, d.get('title'), 18, 'center', 10)
        cy += paragraph(c, x, cy, w, d.get('lead'))
        c.image(x, cy, w, 200, img_of(b, 'img'), 'フレーム内の画像', name='画像'); cy += 200
        return cy - s
    return PAD_Y + framed(c, y + PAD_Y, draw) + PAD_Y


def b_framelist(c, b, p, y):
    d = b['data']; rows = d.get('rows') or []

    def draw(x, cy, w):
        s = cy
        cy += heading(c, x, cy, w, d.get('title'), 18, 'center', 6)
        for i, r in enumerate(rows):
            if i:
                c.line(x, cy, x + w, cy, c.t['ph'], 1)
            cy += 12
            c.open(f'項目{i + 1}')
            cy += paragraph(c, x, cy, w, r)
            c.image(x, cy, w, 160, img_of(b, f'r{i}'), f'画像{i + 1}'); cy += 160 + 12
            c.close()
        return cy - s
    return PAD_Y + framed(c, y + PAD_Y, draw) + PAD_Y


def b_gallery(c, b, p, y):
    d = b['data']; n = int(d.get('count') or 4)
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, 'center', 12)
    gw = (CW - 8) / 2
    for i in range(n):
        c.image(PAD_X + (i % 2) * (gw + 8), cy + (i // 2) * (gw + 8), gw, gw, img_of(b, f'g{i}'), f'画像{i + 1}')
    cy += ((n + 1) // 2) * (gw + 8) - 8
    return cy + PAD_Y - y


def b_reviewlist(c, b, p, y):
    d, t = b['data'], c.t; rows = d.get('rows') or []
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, 'center', 12)

    def draw(x, yy, w):
        s = yy
        for i, r in enumerate(rows):
            if i:
                c.line(x, yy, x + w, yy, t['ph'], 1)
            yy += 10
            c.open(f'口コミ{i + 1}')
            c.image(x, yy, 100, 80, img_of(b, f'rv{i}'), '画像')
            hh = c.text(x + 110, yy, w - 110, r, 14, 400, t['body'], lh=1.75, name='口コミ本文')
            c.close()
            yy += max(80, hh) + 10
        return yy - s
    cy += framed(c, cy, draw, pad=(2, 12)) + 14
    bw = min(280, CW)
    button(c, (W - bw) / 2, cy, bw, 50, (d.get('cta') or '') + '　＋', name='もっと見る', outline=True, pill=True,
           fill='#D8CFCB', color=t['body'], size=15)
    return cy + 50 + PAD_Y - y


def b_modal(c, b, p, y):
    d, t = b['data'], c.t
    top = y + PAD_Y
    mark = len(c.out)
    x, w = PAD_X + 16 + 16, CW - 64
    cy = top + 30 + 20
    cy += heading(c, x, cy, w, d.get('title'), 18, 'center', 10)
    cy += paragraph(c, x, cy, w, d.get('lead'))
    cy += 6
    bw = min(200, w)
    button(c, x + (w - bw) / 2, cy, bw, 40, d.get('cta'), name='閉じる', outline=True, pill=True, fill='#D8CFCB',
           color='#57504E', size=14)
    cy += 40 + 20
    body = c.out[mark:]; del c.out[mark:]
    c.rect(PAD_X, top, CW, cy + 30 - top, fill='#1E1A19', opacity=0.62, name='モーダル背景')
    c.rect(PAD_X + 16, top + 30, CW - 32, cy - top - 30, fill=t['bg'], name='モーダル')
    c.out += body
    return cy + 30 + PAD_Y - y


def slider(c, b, y, has_text):
    t = c.t; d = b['data']; slides = slides_of(d)
    iw = CW * 0.74; ix = PAD_X + CW * 0.13
    sw, sh = slot_size(b, 's')
    imh = (iw - 24) * sh / sw
    s0 = slides[0]
    mark = len(c.out)
    cy = y + 12
    c.image(ix + 12, cy, iw - 24, imh, img_of(b, 's0'), 'スライド1 画像', name='スライド画像'); cy += imh
    if has_text and s0.get('text'):
        cy += 10 + c.text(ix + 12, cy + 10, iw - 24, s0.get('text'), 12, 400, t['body'], lh=1.75, name='スライド説明文')
    if s0.get('btn'):
        cy += 10 + button(c, ix + 12, cy + 10, iw - 24, 44, s0['btn'], name='スライドボタン', size=13)
    cy += 12
    body = c.out[mark:]; del c.out[mark:]
    h = cy - y
    c.open('スライド1')
    c.rect(ix, y, iw, h, fill='#FCFAF9', stroke=t['line'])
    c.out += body
    c.close()
    if len(slides) > 1:                                       # 次スライドのチラ見せ
        px = ix + iw + 8; pw = PAD_X + CW - px
        c.open('スライド2（チラ見せ）')
        c.rect(px, y, pw + 2, h, fill='#FCFAF9', stroke=t['line'])
        c.rect(px + 8, y + 12, pw - 6, imh, fill=t['ph'])
        c.close()
    cy = y + h + 14
    c.open('ページ送り')
    n = len(slides); dots_w = n * 12 + (n - 1) * 8
    total = 32 + 14 + dots_w + 14 + 32; x0 = (W - total) / 2
    for xx, ch in ((x0, '‹'), (x0 + total - 32, '›')):
        c.circle(xx + 16, cy + 16, 15.5, fill=t['bg'], stroke='#DCD4D0', sw=1)
        c.text(xx, cy + 4, 32, ch, 16, 400, '#57504E', 'center', 1.5)
    for i in range(n):
        c.circle(x0 + 46 + i * 20 + 6, cy + 16, 6, fill='#57504E' if i == 0 else '#D2C9C5')
    c.close()
    return cy + 32 - y


def b_slider(c, b, p, y):
    d = b['data']; cy = y + PAD_Y
    cy += heading(c, PAD_X, cy, CW, d.get('title'), 24, mb=12) if b['type'] != 'image-slider' else 0
    cy += slider(c, b, cy, b['type'] != 'image-slider')
    return cy + PAD_Y - y


def step_badge(c, x, y, i, h=None):
    t = c.t
    c.rect(x, y, 51, h or 44, fill=t['primary'], name=f'STEP{i + 1}_バッジ')
    c.text(x, y + 5, 51, 'STEP', 11, 400, t['onPrimary'], 'center', 1.3)
    c.text(x, y + 18, 51, str(i + 1), 20, 700, t['onPrimary'], 'center', 1.2)


def b_flow(c, b, p, y):
    d, t = b['data'], c.t; steps = d.get('steps') or []
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, mb=12)
    for i, s in enumerate(steps):
        c.open(f'STEP{i + 1}')
        cy += 16
        step_badge(c, PAD_X, cy, i)
        tx = PAD_X + 51 + 12; tw = CW - 63
        hh = c.text(tx, cy, tw, s, 14, 400, t['body'], lh=1.75, name='ステップ説明')
        c.image(tx, cy + hh + 8, tw, 120, img_of(b, f'st{i}'), f'STEP{i + 1} 画像')
        cy += max(44, hh + 8 + 120) + 16
        c.line(PAD_X, cy, PAD_X + CW, cy, t['ph'], 1)
        c.close()
    return cy + PAD_Y - y


def b_flowtab(c, b, p, y):
    d, t = b['data'], c.t; steps = d.get('steps') or []
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, mb=12)
    tw = CW / 2
    c.open('タブ')
    c.rect(PAD_X, cy, tw, 44, fill=t['primary'], stroke=t['primary'])
    c.rect(PAD_X + tw, cy, tw, 44, fill=t['bg'], stroke=t['primary'])
    c.text(PAD_X, cy + 11, tw, d.get('t1'), 16, 500, t['onPrimary'], 'center', 1.4)
    c.text(PAD_X + tw, cy + 11, tw, d.get('t2'), 16, 500, t['primary'], 'center', 1.4)
    c.close()
    cy += 44
    for i, s in enumerate(steps):
        c.open(f'STEP{i + 1}')
        cy += 16
        step_badge(c, PAD_X, cy, i)
        hh = c.text(PAD_X + 63, cy, CW - 63, s, 14, 400, t['body'], lh=1.75, name='ステップ説明')
        cy += max(44, hh) + 16
        c.line(PAD_X, cy, PAD_X + CW, cy, t['ph'], 1)
        c.close()
    return cy + PAD_Y - y


def b_accordion(c, b, p, y):
    d, t = b['data'], c.t; faq = b['type'] == 'faq'
    items = [it if isinstance(it, dict) else {'q': str(it), 'a': ''} for it in d.get('items') or []]
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, mb=12)
    for i, it in enumerate(items):
        c.open(f'項目{i + 1}')
        mark = len(c.out)
        qx = PAD_X + 12 + (18 if faq else 0); qw = CW - 24 - (18 if faq else 0) - 22
        hh = c.text(qx, cy + 14, qw, it.get('q'), 14, 400, t['body'], lh=1.5, name='質問' if faq else '項目見出し')
        bh = max(hh, 21) + 28
        body = c.out[mark:]; del c.out[mark:]
        c.rect(PAD_X, cy, CW, bh, fill=t['bg'], stroke='#D8CFCB', name='項目枠')
        c.out += body
        if faq:
            c.text(PAD_X + 12, cy + 14, 16, 'Q', 14, 700, t['accent'], lh=1.5)
        c.text(PAD_X + CW - 30, cy + 14, 18, '＋', 14, 400, '#9A908C', 'center', 1.5)
        cy += bh
        if it.get('a'):
            ax = PAD_X + 12 + (18 if faq else 0)
            if faq:
                c.text(PAD_X + 12, cy + 10, 16, 'A', 12.7, 700, t['accent'], lh=1.75)
            cy += 10 + c.text(ax, cy + 10, CW - 24 - (18 if faq else 0), it['a'], 12.7, 400, '#57504E', lh=1.75,
                              name='回答' if faq else '開いた中身')
        cy += 10
        c.close()
    return cy + PAD_Y - y


def b_video(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, mb=12)
    h = CW * 9 / 16
    c.image(PAD_X, cy, CW, h, img_of(b, 'thumb'), 'YouTube 16:9', name='動画サムネイル')
    c.open('再生ボタン')
    c.rect(W / 2 - 30, cy + h / 2 - 21, 60, 42, fill='#FF0000', rx=10)
    cx, cc = W / 2, cy + h / 2
    c.out.append(f'<path d="M{c.n(cx - 8)} {c.n(cc - 10)} L{c.n(cx + 12)} {c.n(cc)} L{c.n(cx - 8)} {c.n(cc + 10)} Z" '
                 f'fill="#FFFFFF"/>')
    c.close()
    return cy + h + PAD_Y - y


def field(c, x, y, w, label, h=58, name='入力欄', content=None):
    t = c.t
    c.open(name)
    lh = c.text(x, y, w - 50, label, 16, 700, t['ink'], lh=1.5, name='項目名')
    lw = min(w - 50, text_w(label or '', 16))
    c.rect(x + lw + 8, y + 3, 34, 18, fill=REQ_RED, name='必須')
    c.text(x + lw + 8, y + 3, 34, '必須', 12, 400, '#FFFFFF', 'center', 1.5)
    y += lh + 8
    mark = len(c.out)
    ch = c.text(x + 12, y + 12, w - 24, content, 14, 400, t['body'], lh=1.8, name='初期メッセージ') if content else 0
    body = c.out[mark:]; del c.out[mark:]
    h = max(h, ch + 24)
    c.rect(x, y, w, h, fill=t['bg'], stroke='#D6CDC9', name='入力枠')
    c.out += body
    c.close()
    return lh + 8 + h


def b_inviteform(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, 'center', 0)
    for f in ('f1', 'f2'):
        cy += 16 + field(c, PAD_X, cy + 16, CW, d.get(f), name=d.get(f) or f)
    cy += 16 + field(c, PAD_X, cy + 16, CW, d.get('f3'), h=140, name='メッセージ欄', content=d.get('msg'))
    cy += 6 + paragraph(c, PAD_X, cy + 6, CW, '初期メッセージ（送信文テンプレート）', 12, 0, color=t['sub'], name='注記')
    cy += 16 + c.text(PAD_X, cy + 16, CW, '紹介方法選択', 16, 700, t['ink'], lh=1.5)
    for lab, col in ((d.get('cta'), LINE_GREEN), ('メールで送る', '#57504E'), ('リンクでシェア', '#57504E')):
        cy += 12 + button(c, PAD_X, cy + 12, CW, 69, lab, name=lab or '送信', fill=col, size=18)
    return cy + PAD_Y - y


def b_guestform(c, b, p, y):
    d = b['data']
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, 'center', 0)
    for f in ('f1', 'f2'):
        cy += 16 + field(c, PAD_X, cy + 16, CW, d.get(f), name=d.get(f) or f)
    cy += 16 + button(c, PAD_X, cy + 16, CW, 69, d.get('cta'))
    return cy + PAD_Y - y


def b_code(c, b, p, y):
    d, t = b['data'], c.t
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, 'center', 12)
    cw_ = min(CW, text_w(d.get('code', ''), 20) + 64)
    c.rect((W - cw_) / 2, cy, cw_, 60, fill=t['bg'], stroke=t['line'], name='コード枠')
    c.text((W - cw_) / 2, cy + 15, cw_, d.get('code'), 20, 700, t['ink'], 'center', 1.5, name='コード', ls=1)
    cy += 60 + 16
    bw = min(CW, text_w(d.get('cta', ''), 16) + 48)
    button(c, (W - bw) / 2, cy, bw, 50, d.get('cta'), name='コピーボタン', outline=True, size=16)
    return cy + 50 + PAD_Y - y


def b_cta(c, b, p, y):
    d = b['data']
    cy = y + PAD_Y + heading(c, PAD_X, y + PAD_Y, CW, d.get('title'), 24, 'center', 12)
    cy += button(c, PAD_X, cy, CW, 69, d.get('cta'))
    return cy + PAD_Y - y


def b_button(c, b, p, y):
    return PAD_Y + button(c, PAD_X, y + PAD_Y, CW, 69, b['data'].get('label')) + PAD_Y


def b_terms(c, b, p, y):
    d, t = b['data'], c.t; warn = b['type'] == 'notice-list'
    cy = y + PAD_Y
    c.text(PAD_X, cy, 24, '⚠' if warn else '❶', 18, 500, t['ink'], lh=1.6)
    cy += heading(c, PAD_X + 28, cy, CW - 28, d.get('title'), 18, mb=10)
    mark = len(c.out)
    yy = cy + 14
    for i, s in enumerate(d.get('bullets') or []):
        c.circle(PAD_X + 14 + 3, yy + 14 * 1.85 / 2, 2, fill=t['body'])
        yy += c.text(PAD_X + 28, yy, CW - 42, s, 14, 400, t['body'], lh=1.85, name=f'項目{i + 1}') + 6
    yy += 8
    body = c.out[mark:]; del c.out[mark:]
    c.rect(PAD_X, cy, CW, yy - cy, fill=t['bg'], stroke='#D6CDC9', name='規約枠')
    c.out += body
    return yy + PAD_Y - y


def b_footer(c, b, p, y):
    d, t = b['data'], c.t
    c.rect(0, y, W, 74, fill=t['footer'])
    c.text(PAD_X, y + 20, 160, d.get('name') or p.get('title', ''), 12, 400, t['onFooter'], lh=1.6, name='表示名', maxlines=1)
    links = [d.get('a'), d.get('b')]
    x = W - PAD_X
    for s in reversed([l for l in links if l]):
        w = text_w(s, 12)
        c.text(x - w, y + 20, w + 2, s, 12, 400, t['onFooter'], lh=1.6, name='リンク')
        x -= w + 16
    return 74


def b_floating(c, b, p, y):
    t = c.t
    c.rect(0, y, W, 85, fill=t['primary'], name='バナー背景')
    c.text(PAD_X, y + (85 - 18 * 1.4) / 2, CW, b['data'].get('cta'), 18, 500, t['onPrimary'], 'center', 1.4,
           name='バナー文言', maxlines=1)
    return 85


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


def render_page(page, spec, scale=3, base_dir='.', x_offset=0):
    """1ページを描画。(svg本文の要素リスト, 幅pt, 高さpt, 警告, ブロックごとの y 範囲) を返す"""
    theme = theme_of(spec)
    c = Canvas(scale, theme, base_dir)
    y = 0; spans = []
    for i, b in enumerate(page['blocks']):
        label = BLOCKS[b['type']]['label']
        st = b.get('style') or {}          # CMS の「スタイル設定」（背景色・透明度・枠線）とリッチテキストの文字色
        c.t = dict(theme)
        if st.get('textColor'):
            c.t.update(ink=st['textColor'], body=st['textColor'], sub=st['textColor'])
        c.open(f"{i + 1:02d}_{label}")
        mark = len(c.out)
        h = SHAPES[b['type']](c, b, page, y)
        if b.get('minH') and b['minH'] > h:
            h = b['minH']
        body = c.out[mark:]; del c.out[mark:]
        op = st.get('bgOpacity')
        c.rect(0, y, W, h, fill=st.get('bg') or theme['bg'], name='背景', opacity=None if op in (None, 100) else op / 100)
        c.out += body
        if st.get('border'):
            c.rect(0.5, y + 0.5, W - 1, h - 1, stroke=st.get('borderColor') or theme['line'], sw=1, name='枠線')
        c.close()
        spans.append((y, h))
        y += h
    c.t = theme
    return c.out, W, y, c.warn, spans


def svg_doc(groups, width_pt, height_pt, scale):
    w, h = round(width_pt * scale), round(height_pt * scale)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n' + '\n'.join(groups) + '\n</svg>\n')
