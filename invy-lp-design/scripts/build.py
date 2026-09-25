#!/usr/bin/env python3
"""spec.json から、Figma 用 SVG・CMS 入稿シート・プレビュー HTML をまとめて書き出す。

使い方:
  python3 scripts/build.py <spec.json> [--out <出力フォルダ>] [--scale 3] [--zip]

出力（<出力フォルダ>/ 以下）:
  <案件>_<ページ>_figma.svg   … ページ単体。Figma にドラッグ＆ドロップで取り込む
  <案件>_figma_all.svg        … 全ページを横並びにしたもの（ペアで渡すとき用）
  <案件>_cms_sheet.md / .csv  … CMS 入稿シート（ブロック順・CMSパーツ・入力内容・画像）
  <案件>_preview.html         … 壁打ち用のプレビュー（デザイン＋構成表）
  <案件>_handoff.zip          … --zip 指定時。上記一式
"""
import argparse, copy, csv, datetime, html, io, json, os, re, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog import BLOCKS, PAGE_LABEL, PAGE_SETTINGS, COLOR_HOWTO, image_slots, defaults  # noqa: E402
from render import render_page, svg_doc  # noqa: E402

STATE = {'keep': 'KEEP（既存のまま）', 'mod': 'MOD（既存を修正）', 'new': 'NEW（新規追加）', 'plain': '—'}


def safe(s):
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(s or '').strip()) or '構成案'


# ---------------------------------------------------------------- 読み込みと検証
def normalize(spec):
    errors, warns = [], []
    pages = spec.get('pages') or []
    if not pages:
        errors.append('pages が空です')
    for pi, p in enumerate(pages):
        pt = p.get('pageType')
        if pt not in PAGE_LABEL:
            errors.append(f'pages[{pi}].pageType は inviter か guest にしてください（現在: {pt}）'); continue
        p.setdefault('title', spec.get('project', ''))
        for bi, b in enumerate(p.get('blocks') or []):
            where = f'{PAGE_LABEL[pt]} #{bi + 1}'
            t = b.get('type')
            if t not in BLOCKS:
                errors.append(f'{where}: type "{t}" はカタログにありません（references/03-cms-blocks.md を参照）'); continue
            cat = BLOCKS[t]
            if cat['page'] not in ('both', pt):
                errors.append(f'{where}: 「{cat["label"]}」は{PAGE_LABEL[cat["page"]]}専用のパーツです')
            given = b.get('data') or {}
            known = {f[0] for f in cat['fields']} | set(defaults(t)) | {'count'}
            for k in given:
                if k not in known:
                    warns.append(f'{where}: 「{cat["label"]}」に項目 "{k}" はありません（無視されます）')
            d = defaults(t); d.update(given); b['data'] = d
            b.setdefault('state', 'plain')
            if b['state'] not in STATE:
                warns.append(f'{where}: state "{b["state"]}" は keep / mod / new / plain のいずれか'); b['state'] = 'plain'
            if t in ('button', 'client-site-link') and (not d.get('href') or not d.get('measure')):
                warns.append(f'{where}: CTA の遷移先（href）と計測方法（measure）が未確定です')
        p['blocks'] = [b for b in p.get('blocks') or [] if b.get('type') in BLOCKS]
        ps = p.get('settings') or {}
        miss = [n for k, n in (('description', 'description'), ('ogp', 'OGP画像')) if not ps.get(k)]
        if miss:
            warns.append(f"{PAGE_LABEL[pt]}: ページ設定の必須項目が未定（{'・'.join(miss)}）")
    return errors, warns


# ---------------------------------------------------------------- CMS 入稿シート
def field_lines(b):
    d = b['data']; out = []
    for key, name, kind in BLOCKS[b['type']]['fields']:
        v = d.get(key)
        if kind in ('text', 'multi'):
            out.append((name, '' if v is None else 'あり' if v is True else 'なし' if v is False else str(v)))
        elif kind == 'list':
            for i, s in enumerate(v or []):
                out.append((f'{name} {i + 1}', str(s)))
        elif kind == 'items':
            for i, it in enumerate(v or []):
                it = it if isinstance(it, dict) else {'q': str(it), 'a': ''}
                out.append((f'{name} {i + 1} 見出し', it.get('q', '')))
                out.append((f'{name} {i + 1} 中身', it.get('a', '')))
        elif kind == 'slides':
            for i, s in enumerate(v or []):
                s = s if isinstance(s, dict) else {'text': str(s)}
                out.append((f'{name} {i + 1} 説明文', s.get('text', '')))
                if s.get('btn'):
                    out.append((f'{name} {i + 1} ボタン', s['btn']))
    return out


def style_lines(b):
    st = b.get('style') or {}; out = []
    if st.get('bg'):
        out.append(('スタイル設定：背景色', st['bg'] + (f"（透明度 {st['bgOpacity']}%）" if st.get('bgOpacity') not in (None, 100) else '')))
    if st.get('border'):
        out.append(('スタイル設定：枠線で囲う', 'ON'))
    if st.get('padding') is not None:
        out.append(('スタイル設定：余白（全体）', f"{st['padding']}px"))
    if st.get('textColor'):
        out.append(('リッチテキスト：文字色', st['textColor']))
    for k, lab in (('id', 'コンポーネントのID'), ('label', 'コンポーネントのラベル')):
        if b.get(k):
            out.append((lab, str(b[k])))
    if b.get('hidden'):
        out.append(('非表示にする', 'ON'))
    return out


def image_lines(b, scale):
    imgs = b.get('images') or {}; out = []
    for slot, name, w, h in image_slots(b['type'], b['data']):
        src = imgs.get(slot)
        out.append((name, os.path.basename(src) if src else '未支給',
                    f'{w}×{h}pt（{round(w * scale)}×{round(h * scale)}px 相当）'))
    return out


def sheet_md(spec, scale):
    L = [f"# CMS入稿シート：{spec.get('project', '')}", '',
         f"- 生成日時：{datetime.datetime.now():%Y-%m-%d %H:%M}",
         f"- 配色：{'ブランド配色' if (spec.get('theme') or {}).get('mode') == 'brand' else 'ワイヤー（無彩色）'}",
         '- 画像サイズはツール上の比率。CMS 側の推奨入稿サイズで最終確認すること', '']
    th = spec.get('theme') or {}
    if th.get('mode') == 'brand':
        L += ['## 配色の入れ方（CMS 上の手段）', '',
              f"基調色 `{th.get('primary', '')}` をボタン・バナー等に当てている。CMS では次の手段で入れる。", '',
              '| 変えたいもの | CMS でのやり方 |', '|---|---|']
        L += [f'| {a} | {b} |' for a, b in COLOR_HOWTO]
        L += ['']
    for p in spec['pages']:
        L += [f"## {PAGE_LABEL[p['pageType']]}：{p.get('title', '')}", '']
        ps = p.get('settings') or {}
        L += ['### ページ設定', '', '| CMS の項目 | 内容 |', '|---|---|']
        for k, n, m in PAGE_SETTINGS:
            v = ps.get(k, p.get('title') if k == 'title' else None)
            L.append(f"| {n} | {str(v).replace(chr(10), '<br>').replace('|', '／') if v not in (None, '') else '（未定・' + m + '）'} |")
        L += ['', '### ブロック一覧', '',
              '| No | CMSパーツ | CMSクラス | 状態 | 意図 |', '|---|---|---|---|---|']
        for i, b in enumerate(p['blocks']):
            cat = BLOCKS[b['type']]
            L.append(f"| {i + 1:02d} | {cat['label']} | `invyBlockEditor-{cat['cms'][0]}` | {STATE[b['state']]} | "
                     f"{(b.get('note') or '').replace('|', '／')} |")
        L.append('')
        for i, b in enumerate(p['blocks']):
            cat = BLOCKS[b['type']]
            L += [f"#### {i + 1:02d}. {cat['label']}（{STATE[b['state']]}）", '']
            if b.get('note'):
                L += [f"> 意図：{b['note']}", '']
            L += ['| 入力項目 | 内容 |', '|---|---|']
            for k, v in field_lines(b) + style_lines(b):
                L.append(f"| {k} | {v.replace(chr(10), '<br>').replace('|', '／') or '（空欄）'} |")
            il = image_lines(b, scale)
            if il:
                L += ['', '| 画像 | ファイル | サイズ |', '|---|---|---|']
                L += [f'| {a} | {f} | {s} |' for a, f, s in il]
            L.append('')
    if spec.get('outOfCms'):
        L += ['## CMS外の要望（テンプレートパーツで実現できないもの）', '']
        L += [f'- {x}' for x in spec['outOfCms']]
        L.append('')
    return '\n'.join(L)


def sheet_csv(spec, scale):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['ページ', 'No', 'CMSパーツ', 'CMSクラス', '状態', '区分', '項目', '内容', 'サイズ', '意図'])
    for p in spec['pages']:
        ps = p.get('settings') or {}
        for k, n, m in PAGE_SETTINGS:
            v = ps.get(k, p.get('title') if k == 'title' else '')
            w.writerow([PAGE_LABEL[p['pageType']], 0, 'ページ設定', '', '', '設定', n, v or '', '', m])
        for i, b in enumerate(p['blocks']):
            cat = BLOCKS[b['type']]
            base = [PAGE_LABEL[p['pageType']], i + 1, cat['label'], 'invyBlockEditor-' + cat['cms'][0], STATE[b['state']]]
            for k, v in field_lines(b):
                w.writerow(base + ['テキスト', k, v, '', b.get('note', '')])
            for k, v in style_lines(b):
                w.writerow(base + ['設定', k, v, '', b.get('note', '')])
            for a, f, s in image_lines(b, scale):
                w.writerow(base + ['画像', a, f, s, b.get('note', '')])
    return '﻿' + buf.getvalue()   # Excel で文字化けしないよう BOM 付き


# ---------------------------------------------------------------- プレビュー HTML
PREVIEW_CSS = """
:root{--bg:#F5F2EF;--panel:#FFFFFF;--ink:#231D1C;--muted:#7A6E6B;--line:#E2D9D5;--accent:#DE5C5C;
  --keep:#8C817D;--mod:#DE5C5C;--new:#2F7367;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1A1616;--panel:#231E1D;--ink:#F0E9E6;
  --muted:#A79995;--line:#3A3130;--accent:#F27B76;--keep:#A79995;--mod:#F27B76;--new:#63A99B;}}
:root[data-theme="dark"]{--bg:#1A1616;--panel:#231E1D;--ink:#F0E9E6;--muted:#A79995;--line:#3A3130;--accent:#F27B76;
  --keep:#A79995;--mod:#F27B76;--new:#63A99B;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.7 'Noto Sans JP',system-ui,sans-serif}
header{padding:20px 16px 8px;max-width:1180px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px} .sub{color:var(--muted);font-size:12.5px}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 0} nav a{color:var(--ink);text-decoration:none;border:1px solid var(--line);
  background:var(--panel);padding:5px 12px;border-radius:999px;font-size:12.5px} nav a:hover{border-color:var(--accent);color:var(--accent)}
section.page{max-width:1180px;margin:0 auto;padding:16px;display:grid;grid-template-columns:minmax(0,375px) minmax(0,1fr);gap:24px;align-items:start}
section.page h2{grid-column:1/-1;font-size:16px;margin:12px 0 0}
.phone{background:#fff;box-shadow:0 12px 36px rgba(35,29,28,.16);border-radius:4px;overflow:hidden}
.phone svg{display:block;width:100%;height:auto}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:12.5px}
th,td{text-align:left;padding:8px 10px;border-top:1px solid var(--line);vertical-align:top}
th{background:transparent;color:var(--muted);font-weight:700;border-top:0}
.no{font-family:ui-monospace,monospace;color:var(--muted);white-space:nowrap}
.cls{font-family:ui-monospace,monospace;font-size:11px;color:var(--muted);word-break:break-all}
.st{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}
.st.keep{color:var(--keep)} .st.mod{color:var(--mod)} .st.new{color:var(--new)} .st.plain{color:var(--muted)}
.warn{max-width:1180px;margin:8px auto 0;padding:10px 14px;border-left:3px solid var(--accent);background:var(--panel);font-size:12.5px}
.side{position:sticky;top:12px}
@media (max-width:760px){section.page{grid-template-columns:1fr}.side{position:static}}
"""


def preview_html(spec, page_svgs, warns):
    proj = html.escape(spec.get('project', '構成案'))
    parts = [f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{proj} LP構成案</title>'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900'
             '&family=Zen+Kaku+Gothic+New:wght@500;700;900&display=swap">'
             f'<style>{PREVIEW_CSS}</style></head><body>',
             f'<header><h1>{proj}：紹介LP構成案</h1><div class="sub">生成 {datetime.datetime.now():%Y-%m-%d %H:%M}'
             f'／表示は実機375pt幅。Figma用SVGは幅{round(375 * spec.get("_scale", 3))}px</div><nav>']
    for i, p in enumerate(spec['pages']):
        parts.append(f'<a href="#p{i}">{PAGE_LABEL[p["pageType"]]}</a>')
    parts.append('</nav></header>')
    if warns:
        parts.append('<div class="warn"><b>未確定・要確認</b><br>' + '<br>'.join(html.escape(w) for w in warns) + '</div>')
    for i, (p, svg) in enumerate(zip(spec['pages'], page_svgs)):
        rows = ''.join(
            f'<tr><td class="no">{j + 1:02d}</td><td>{html.escape(BLOCKS[b["type"]]["label"])}'
            f'<div class="cls">invyBlockEditor-{BLOCKS[b["type"]]["cms"][0]}</div></td>'
            f'<td><span class="st {b["state"]}">{b["state"].upper() if b["state"] != "plain" else "—"}</span></td>'
            f'<td>{html.escape(b.get("note") or "")}</td></tr>' for j, b in enumerate(p['blocks']))
        parts.append(f'<section class="page" id="p{i}"><h2>{PAGE_LABEL[p["pageType"]]}：{html.escape(p.get("title", ""))}</h2>'
                     f'<div class="phone">{svg.split("?>", 1)[-1]}</div>'
                     f'<div class="side"><table><thead><tr><th>No</th><th>CMSパーツ</th><th>状態</th><th>意図</th></tr></thead>'
                     f'<tbody>{rows}</tbody></table></div></section>')
    parts.append('</body></html>')
    return ''.join(parts)


# ---------------------------------------------------------------- メイン
def build(spec_path, out_dir=None, scale=3, make_zip=False):
    with open(spec_path, encoding='utf-8') as f:
        spec = json.load(f)
    base = os.path.dirname(os.path.abspath(spec_path))
    out_dir = out_dir or os.path.join(base, 'out')
    os.makedirs(out_dir, exist_ok=True)
    spec = copy.deepcopy(spec); spec['_scale'] = scale
    errors, warns = normalize(spec)
    if errors:
        print('エラー（書き出しを中止）:', *errors, sep='\n  - ')
        sys.exit(1)
    proj = safe(spec.get('project'))
    files, page_svgs, all_groups, x = [], [], [], 0
    GAP = 100
    heights = []
    for p in spec['pages']:
        groups, w, h, rwarn, _ = render_page(p, spec, scale, base)
        warns += [f"{PAGE_LABEL[p['pageType']]}: {m}" for m in rwarn]
        svg = svg_doc(groups, w, h, scale)
        name = f"{proj}_{PAGE_LABEL[p['pageType']]}_figma.svg"
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
            f.write(svg)
        files.append(name); page_svgs.append(svg); heights.append(h)
        all_groups.append(f'<g id="{PAGE_LABEL[p["pageType"]]}" transform="translate({round(x * scale)},0)">')
        all_groups += groups
        all_groups.append('</g>')
        x += w + GAP
    if len(spec['pages']) > 1:
        name = f'{proj}_figma_all.svg'
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
            f.write(svg_doc(all_groups, x - GAP, max(heights), scale))
        files.append(name)
    for name, body in ((f'{proj}_cms_sheet.md', sheet_md(spec, scale)), (f'{proj}_cms_sheet.csv', sheet_csv(spec, scale)),
                       (f'{proj}_preview.html', preview_html(spec, page_svgs, warns))):
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
            f.write(body)
        files.append(name)
    if make_zip:
        zname = f'{proj}_handoff.zip'
        with zipfile.ZipFile(os.path.join(out_dir, zname), 'w', zipfile.ZIP_DEFLATED) as z:
            for n in files:
                z.write(os.path.join(out_dir, n), n)
            z.write(spec_path, 'spec.json')
        files.append(zname)
    print('書き出し先:', out_dir)
    for n in files:
        print('  -', n)
    for p, h in zip(spec['pages'], heights):
        print(f"  {PAGE_LABEL[p['pageType']]}: {len(p['blocks'])}ブロック / {round(375 * scale)}×{round(h * scale)}px")
    if warns:
        print('要確認:', *warns, sep='\n  - ')
    return out_dir, files, warns


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec')
    ap.add_argument('--out')
    ap.add_argument('--scale', type=float, default=3)
    ap.add_argument('--zip', action='store_true')
    a = ap.parse_args()
    build(a.spec, a.out, a.scale, a.zip)
