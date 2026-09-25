#!/usr/bin/env python3
"""既存の invy 公開ページの HTML から、spec.json のページ（ブロック構成と文言）を復元する。

使い方:
  python3 scripts/import_invy.py <page.html> [--spec 既存spec.json] [--out 出力spec.json] [--project 案件名]

- `invyBlockEditor-<クラス>` を持つ要素を、入れ子の外側優先でブロックとして拾う
- `data-page-type`（1=紹介者 / 2=ゲスト）でページ種別を判定。無ければフォームの種類で推定
- `data-surveys` からフォーム項目名と初期メッセージを取る
- 取り込んだブロックはすべて state=keep。画像は元のファイル名を note に残す（画像自体は取り込まない）
標準ライブラリのみで動く。
"""
import argparse, json, os, re, sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog import BLOCKS, CMS_TO_TYPE, defaults  # noqa: E402

PREFIX = 'invyBlockEditor-'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.kids, self.text = tag, dict(attrs), parent, [], []

    @property
    def classes(self):
        return (self.attrs.get('class') or '').split()

    def walk(self):
        for k in self.kids:
            if isinstance(k, Node):
                yield k
                yield from k.walk()

    def select(self, sel):
        """カンマ区切りの `tag` / `.class` / `tag.class` だけに対応した簡易セレクタ"""
        pats = []
        for s in sel.split(','):
            s = s.strip()
            tag, _, cls = s.partition('.')
            pats.append((tag or None, cls or None))
        return [n for n in self.walk()
                if any((t is None or n.tag == t) and (c is None or c in n.classes) for t, c in pats)]

    def first(self, sel):
        r = self.select(sel)
        return r[0] if r else None

    def txt(self):
        out = []

        def rec(n):
            for k in n.kids:
                if isinstance(k, Node):
                    if k.tag not in ('script', 'style'):
                        rec(k)
                else:
                    out.append(k)
        rec(self)
        return re.sub(r'\s+', ' ', ''.join(out)).strip()


class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('#root', {}, None); self.cur = self.root; self.title = ''; self._in_title = False

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur); self.cur.kids.append(n)
        if tag == 'title':
            self._in_title = True
        if tag not in VOID:
            self.cur = n

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        self.cur.kids.append(data)


def type_of(n):
    for c in n.classes:
        if c.startswith(PREFIX) and c[len(PREFIX):] in CMS_TO_TYPE:
            return c[len(PREFIX):], CMS_TO_TYPE[c[len(PREFIX):]]
    return None


def parse(html_text):
    p = Parser(); p.feed(html_text)
    root = p.root
    pt_el = next((n for n in root.walk() if 'data-page-type' in n.attrs), None)
    pt_raw = pt_el.attrs.get('data-page-type') if pt_el else None
    surveys = []
    s_el = next((n for n in root.walk() if 'data-surveys' in n.attrs), None)
    if s_el:
        try:
            surveys = json.loads(s_el.attrs['data-surveys']) or []
        except Exception:
            surveys = []

    hits = [(n, *type_of(n)) for n in root.walk() if type_of(n)]
    ids = {id(n) for n, _, _ in hits}

    def has_hit_ancestor(n):
        a = n.parent
        while a is not None:
            if id(a) in ids:
                return True
            a = a.parent
        return False
    tops = [h for h in hits if not has_hit_ancestor(h[0])]

    blocks, counts = [], {}
    for el, cms, t in tops:
        counts[cms] = counts.get(cms, 0) + 1
        d = defaults(t); note = []
        head = el.first('h1,h2,h3,h4,.invyBlockEditor-headline-title,.title2,.flow-title,.invite-form-heading')
        if head and 'title' in d and head.txt():
            d['title'] = head.txt()
        imgs = [os.path.basename((i.attrs.get('src') or '').split('?')[0]) for i in el.select('img') if i.attrs.get('src')]
        if imgs:
            note.append('既存画像: ' + ', '.join(imgs[:6]))
        if 'slides' in d:
            seen, uniq = set(), []
            for s in el.select('.swiper-slide'):
                tx = s.txt()
                if tx and tx not in seen:
                    seen.add(tx); uniq.append(tx)
            n_sl = len(el.select('.swiper-slide'))
            if uniq:
                d['slides'] = [{'text': x} for x in uniq[:10]]
            elif n_sl:
                d['slides'] = [{'text': ''} for _ in range(min(n_sl, 10))]
        if t == 'text-editor':
            t2 = el.txt()
            if t2:
                d['title'], d['lead'] = (t2, '') if len(t2) <= 30 else ('', t2[:240])
        if t == 'benefits':
            items = [(x.first('.title3,.title4') or x).txt() for x in el.select('.benefit-item')]
            items = [x for x in items if x]
            if items[:1]:
                d['a'] = items[0][:60]
            if items[1:2]:
                d['b'] = items[1][:60]
        if t in ('flow', 'flow-tab'):
            steps = [x.txt() for x in el.select('.stepBlock,.stepBlock2,.tabs-block') if x.txt()]
            if steps:
                d['steps'] = [s[:120] for s in steps[:6]]
        if t in ('please-read', 'notice-list'):
            lis = [x.txt() for x in el.select('li') if x.txt()]
            if lis:
                d['bullets'] = lis[:20]
        if t in ('invitation-detail', 'faq', 'accordion-list'):
            qs = [x.txt() for x in el.select('.invyBlockEditor-invitation-detail-list-header-title-text,'
                                            '.invyBlockEditor-faq-list-item-title,.accordion-list-item-title') if x.txt()]
            ans = [x.txt() for x in el.select('.invyBlockEditor-faq-list-main-text,'
                                             '.invyBlockEditor-invitation-detail-list-item-contents,.accordion-list-main-text')]
            if qs:
                d['items'] = [{'q': q[:120], 'a': (ans[i] if i < len(ans) else '')[:240]} for i, q in enumerate(qs)]
            else:
                tds = [x.txt() for x in el.select('.invyBlockEditor-table-table-td') if x.txt()]
                if tds:
                    d['items'] = [{'q': tds[i][:120], 'a': (tds[i + 1] if i + 1 < len(tds) else '')[:240]}
                                  for i in range(0, len(tds), 2)]
        if t in ('invite-form', 'guest-form'):
            for i, s in enumerate(surveys[:3]):
                if s.get('label'):
                    d[f'f{i + 1}'] = s['label']
            wd = next((s for s in surveys if s.get('default')), None)
            if wd and t == 'invite-form':
                d['msg'] = str(wd['default'])[:300]
            b = el.first('.formBtn-button-text,.guest-send-button,.btn-next')
            if b and b.txt():
                d['cta'] = b.txt()
        if t == 'brand-logo':
            b = el.first('.btn')
            if b and b.txt():
                d['cta'] = b.txt()
        if t == 'invitation-banner':
            b = el.first('.button-text,.kvBtn__text,a')
            if b and b.txt():
                d['cta'] = b.txt()
        if t == 'invitation-code':
            b = el.first('.coupon-code,.invyBlockEditor-invitation-code-main-title')
            if b and b.txt():
                d['code'] = b.txt()
        blocks.append({'type': t, 'state': 'keep', 'note': ' / '.join(note), 'data': d, 'src': cms})

    if pt_raw == '2':
        pt = 'guest'
    elif pt_raw == '1':
        pt = 'inviter'
    elif any(b['type'] == 'guest-form' for b in blocks):
        pt = 'guest'
    else:
        pt = 'inviter'
    title = re.split(r'[|｜]', p.title or '')[0].strip()
    return {'pageType': pt, 'title': title, 'blocks': blocks}, counts, surveys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('html')
    ap.add_argument('--spec', help='追記・置き換え先の spec.json（同じ pageType のページを置き換える）')
    ap.add_argument('--out', help='出力先（省略時は --spec を上書き、無ければ標準出力）')
    ap.add_argument('--project', default='')
    a = ap.parse_args()
    with open(a.html, encoding='utf-8', errors='ignore') as f:
        page, counts, surveys = parse(f.read())
    if not page['blocks']:
        print('invy のブロック（invyBlockEditor-*）が見つかりませんでした。公開ページで DevTools を開き、'
              '<body> か #app の outerHTML をコピーして保存したファイルを渡してください。', file=sys.stderr)
        sys.exit(1)
    if a.spec and os.path.exists(a.spec):
        with open(a.spec, encoding='utf-8') as f:
            spec = json.load(f)
    else:
        spec = {'project': a.project or page['title'] or '案件名', 'theme': {'mode': 'wire'}, 'pages': [], 'outOfCms': []}
    spec['pages'] = [p for p in spec.get('pages', []) if p.get('pageType') != page['pageType']] + [page]
    out = a.out or a.spec
    body = json.dumps(spec, ensure_ascii=False, indent=2)
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            f.write(body)
        print('書き出し:', out)
    else:
        print(body)
    print(f"{page['pageType']}：{len(page['blocks'])}ブロック（" +
          ' / '.join(f'{k}×{v}' if v > 1 else k for k, v in counts.items()) + '）'
          + (f' / フォーム項目 {len(surveys)} 件' if surveys else ''), file=sys.stderr)


if __name__ == '__main__':
    main()
