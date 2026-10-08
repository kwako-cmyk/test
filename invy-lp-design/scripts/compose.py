#!/usr/bin/env python3
"""ブロック庫（blocks/html）から、ページ設計書（page.json）どおりにページ HTML を組み上げる。

使い方:
  python3 scripts/compose.py <page.json> [--out <出力フォルダ>] [--constraints <constraints.json>] [--wire]

- 構成案（グレースケール）：--wire を付けると theme を無視してワイヤー表示（テンプレートのまま）で出す
- デザイン：theme.main / theme.sub / theme.font を当て、images の画像を埋める
- 制約チェック：--constraints（スプレッドシートを書き出したもの）があれば、個数・文字数・必須を確認して警告する

出力：<出力フォルダ>/<案件>_<ページ名>.html（1ページ1ファイル、CSS と画像を埋め込んだ単体 HTML）
標準ライブラリのみ。
"""
import argparse, base64, copy, html, json, mimetypes, os, re, sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCKS = os.path.join(ROOT, 'blocks')
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
FONT_MODES = {'gothic-regular': 'ゴシック／標準', 'gothic-light': 'ゴシック／細め',
              'mincho-regular': '明朝／標準', 'mincho-light': '明朝／細め'}


# ---------------------------------------------------------------- 最小限の DOM
class El:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.kids = tag, dict(attrs or {}), parent, []

    def walk(self):
        for k in self.kids:
            if isinstance(k, El):
                yield k
                yield from k.walk()

    def find(self, pred):
        return [e for e in self.walk() if pred(e)]

    def text(self):
        return ''.join(k if isinstance(k, str) else k.text() for k in self.kids)

    def set_text(self, s):
        """改行は <br> に。文字はエスケープ済みで入れる"""
        self.kids = []
        parts = str(s).split('\n')
        for i, p in enumerate(parts):
            if i:
                self.kids.append(El('br', {}, self))
            self.kids.append(html.escape(p, quote=False))

    def html(self):
        a = ''.join(f' {k}' if v is None else f' {k}="{html.escape(str(v))}"' for k, v in self.attrs.items())
        if self.tag in VOID:
            return f'<{self.tag}{a}>'
        inner = ''.join(k if isinstance(k, str) else k.html() for k in self.kids)
        return f'<{self.tag}{a}>{inner}</{self.tag}>'


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.root = El('#root'); self.cur = self.root; self.raw = False

    def handle_starttag(self, tag, attrs):
        e = El(tag, attrs, self.cur); self.cur.kids.append(e)
        if tag not in VOID:
            self.cur = e
        self.raw = tag in ('style', 'script')

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(El(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent
        self.raw = False

    def handle_data(self, d):
        self.cur.kids.append(d)

    def handle_entityref(self, name):
        self.cur.kids.append(f'&{name};')

    def handle_charref(self, name):
        self.cur.kids.append(f'&#{name};')


def parse(s):
    b = Builder(); b.feed(s); return b.root


def clone(e, parent=None):
    c = El(e.tag, dict(e.attrs), parent)
    c.kids = [k if isinstance(k, str) else clone(k, c) for k in e.kids]
    return c


# ---------------------------------------------------------------- 差し込み
def data_uri(path, base):
    p = path if os.path.isabs(path) else os.path.join(base, path)
    if not os.path.exists(p):
        return None
    mt = mimetypes.guess_type(p)[0] or 'image/png'
    with open(p, 'rb') as f:
        return f'data:{mt};base64,{base64.b64encode(f.read()).decode()}'


def fill(scope, values, prefix, base, warns, where):
    """scope 内の data-field / data-href-field / data-slot を values で埋める。繰り返しの中は prefix='items.'"""
    for key, val in values.items():
        if isinstance(val, list) or isinstance(val, dict):
            continue
        full = prefix + key
        hits = [e for e in scope.walk() if e.attrs.get('data-field') == full and not inside_other_item(e, scope)]
        links = [e for e in scope.walk() if e.attrs.get('data-href-field') == full and not inside_other_item(e, scope)]
        slots = [e for e in scope.walk() if e.attrs.get('data-slot') == full and not inside_other_item(e, scope)]
        if not (hits or links or slots) and full not in KNOWN.get(CUR[0], set()):
            warns.append(f'{where}: 項目「{full}」はこのブロックにありません')
        for e in hits:
            e.set_text(val)
        for e in links:
            e.attrs['href'] = val
        for e in slots:
            uri = data_uri(val, base)
            if uri:
                e.kids = [El('img', {'src': uri, 'alt': ''}, e)]
                e.attrs['data-filled'] = '1'
            else:
                warns.append(f'{where}: 画像が見つかりません「{val}」')


def inside_other_item(e, scope):
    """scope の外側の繰り返し（data-item）の中にある要素は対象外にする（scope 自身が item の場合を除く）"""
    p = e.parent
    while p is not None and p is not scope:
        if 'data-item' in p.attrs:
            return True
        p = p.parent
    return False


def apply_repeat(blk, key, items, base, warns, where):
    conts = [e for e in blk.walk() if e.attrs.get('data-repeat') == key]
    if not conts:
        warns.append(f'{where}: 繰り返し「{key}」はこのブロックにありません')
        return
    cont = conts[0]
    tmpl = [k for k in cont.kids if isinstance(k, El) and 'data-item' in k.attrs]
    if not tmpl:
        return
    others = [k for k in cont.kids if not (isinstance(k, El) and 'data-item' in k.attrs)]
    def keys_of(t):
        return {e.attrs.get(a)[len(key) + 1:] for e in t.walk() for a in ('data-field', 'data-href-field', 'data-slot')
                if (e.attrs.get(a) or '').startswith(key + '.')}

    new = []
    for i, it in enumerate(items):
        # 項目の組み合わせが合うテンプレート（例：小見出しありの行）を選ぶ。同点なら同じ位置のもの
        want = {k for k, v in it.items() if not isinstance(v, (list, dict))}
        pos = min(i, len(tmpl) - 1)
        pick = max(range(len(tmpl)), key=lambda j: (want <= keys_of(tmpl[j]), -len(keys_of(tmpl[j]) ^ want), j == pos))
        c = clone(tmpl[pick], cont)
        here = f'{where} {key}[{i + 1}]'
        fill(c, it, key + '.', base, warns, here)
        left = sorted({e.attrs['data-field'][len(key) + 1:] for e in c.walk()
                       if (e.attrs.get('data-field') or '').startswith(key + '.')} - want)
        if left:
            warns.append(f'{here}: 項目「{"」「".join(left)}」が未入力のため、テンプレートの文言が残ります')
        new.append(c)
    first = next((i for i, k in enumerate(cont.kids) if isinstance(k, El) and 'data-item' in k.attrs), len(cont.kids))
    cont.kids = [k for k in cont.kids[:first] if k in others] + new + [k for k in cont.kids[first:] if k in others]


KNOWN, CUR = {}, ['']


def known_keys(block):
    """メタ情報にある項目（画面に出ていない状態の項目も含む）"""
    if block not in KNOWN:
        m = json.load(open(os.path.join(BLOCKS, 'meta.json'), encoding='utf-8')).get(block, {})
        KNOWN[block] = {f['key'] for f in m.get('fields', [])} | {i['slot'] for i in m.get('images', [])}
    return KNOWN[block]


def build_block(b, base, warns, where):
    known_keys(b['block']); CUR[0] = b['block']
    path = os.path.join(BLOCKS, 'html', b['block'] + '.html')
    if not os.path.exists(path):
        raise SystemExit(f'{where}: ブロック「{b["block"]}」はブロック庫にありません（blocks/inventory.json を参照）')
    root = parse(open(path, encoding='utf-8').read())
    blk = next(e for e in root.walk() if e.tag == 'section')
    fill(blk, b.get('fields') or {}, '', base, warns, where)
    fill(blk, b.get('images') or {}, '', base, warns, where)
    for key, items in (b.get('repeats') or {}).items():
        apply_repeat(blk, key, items, base, warns, where)
    if b.get('note'):
        blk.attrs['data-note'] = b['note']
    return blk


# ---------------------------------------------------------------- 制約チェック
def check(page, constraints, warns):
    if not constraints:
        return
    for i, b in enumerate(page['blocks']):
        where = f"{page['name']} #{i + 1} {b['block']}"
        rules = constraints.get(b['block']) or {}
        for key, items in (b.get('repeats') or {}).items():
            r = rules.get(key) or {}
            if r.get('min') and len(items) < int(r['min']):
                warns.append(f'{where}: 「{key}」は{r["min"]}個以上必要（現在{len(items)}個）')
            if r.get('max') and len(items) > int(r['max']):
                warns.append(f'{where}: 「{key}」は{r["max"]}個まで（現在{len(items)}個）')
        vals = dict(b.get('fields') or {})
        for key, items in (b.get('repeats') or {}).items():
            for it in items:
                for k, v in it.items():
                    vals.setdefault(f'{key}.{k}', v)
        for key, r in rules.items():
            if r.get('maxChars') and key in vals and len(str(vals[key]).replace('\n', '')) > int(r['maxChars']):
                warns.append(f'{where}: 「{key}」は{r["maxChars"]}文字まで（現在{len(str(vals[key]))}文字）')
            if r.get('required') and key not in vals:
                warns.append(f'{where}: 「{key}」は必須です（未入力）')


# ---------------------------------------------------------------- ページ
FONTS_LINK = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700'
              '&family=Noto+Serif+JP:wght@300;400;500;700&family=Roboto:wght@300;400;500;700&display=swap">')


def page_html(spec, page, blocks_html, wire):
    th = {} if wire else (spec.get('theme') or {})
    css = open(os.path.join(BLOCKS, '_base.css'), encoding='utf-8').read()
    vars_ = ''.join(f'--{k}:{th[k]};' for k in ('main', 'sub') if th.get(k))
    font = th.get('font', 'gothic-regular')
    title = html.escape(f"{spec.get('project', '')} {page['name']}{'（構成案）' if wire else ''}")
    return (f'<!doctype html><html lang="ja" data-font="{font}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>{FONTS_LINK}'
            f'<style>{css}\n:root{{{vars_}}}\nbody{{margin:0;background:#e9eaec}}'
            f'.page{{box-shadow:0 10px 30px rgba(0,0,0,.12)}}</style></head><body><div class="page">'
            + '\n'.join(blocks_html) + '</div></body></html>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('page')
    ap.add_argument('--out')
    ap.add_argument('--constraints')
    ap.add_argument('--wire', action='store_true')
    a = ap.parse_args()
    spec = json.load(open(a.page, encoding='utf-8'))
    base = os.path.dirname(os.path.abspath(a.page))
    out = a.out or os.path.join(base, 'out')
    os.makedirs(out, exist_ok=True)
    cons = json.load(open(a.constraints, encoding='utf-8')) if a.constraints and os.path.exists(a.constraints) else None
    warns, files = [], []
    for page in spec['pages']:
        check(page, cons, warns)
        built = []
        for i, b in enumerate(page['blocks']):
            blk = build_block(b, base, warns, f"{page['name']} #{i + 1} {b['block']}")
            built.append(blk.html())
        name = re.sub(r'[\\/:*?"<>|\s]+', '_', f"{spec.get('project', 'page')}_{page['name']}{'_構成案' if a.wire else ''}") + '.html'
        with open(os.path.join(out, name), 'w', encoding='utf-8') as f:
            f.write(page_html(spec, page, built, a.wire))
        files.append(name)
    print('書き出し:', out)
    for n in files:
        print('  -', n)
    if warns:
        print('要確認:', *warns, sep='\n  - ')
    if cons is None:
        print('（制約表なしで実行。個数・文字数のチェックはしていません）')


if __name__ == '__main__':
    main()
