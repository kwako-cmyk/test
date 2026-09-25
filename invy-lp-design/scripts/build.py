#!/usr/bin/env python3
"""spec.json から、Figma 用 SVG・CMS 入稿シート・プレビュー HTML をまとめて書き出す。

使い方:
  python3 scripts/build.py <spec.json> [--out <出力フォルダ>] [--scale 3] [--zip]

出力（<出力フォルダ>/ 以下）:
  <案件>_<ページ>_figma.svg   … 紹介者ページ／ゲストページ単体。Figma にドラッグ＆ドロップで取り込む
  <案件>_OGP_figma.svg        … OGP 画像（1200×630px）
  <案件>_LINE表示イメージ_figma.svg … LINE で送ったときの見え方（イメージ）
  <案件>_figma_all.svg        … 上の4枚を横並びにしたもの（まとめて取り込む用）
  <案件>_cms_sheet.md / .csv  … CMS 入稿シート（ブロック順・CMSパーツ・入力内容・画像）
  <案件>_preview.html         … 壁打ち用のプレビュー（デザイン＋構成表）
  <案件>_handoff.zip          … --zip 指定時。上記一式
"""
import argparse, copy, csv, datetime, html, io, json, os, re, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog import BLOCKS, PAGE_LABEL, PAGE_SETTINGS, COLOR_HOWTO, image_slots, defaults  # noqa: E402
from render import render_page, render_ogp, render_line, svg_doc  # noqa: E402

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
        miss = [n for k, n in (('description', 'description'),) if not ps.get(k)]
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
            if b['type'] == 'kv-image' and not (b.get('images') or {}).get('kv'):
                L += [f"> 入稿方法：Figma の「{i + 1:02d}_{cat['label']}」をデザイナーが仕上げて PNG（幅1125px）で書き出し、"
                      'このコンポーネントに画像1枚で入れる。下の「KV内の◯◯」は画像に入れる文言', '']
            L += ['| 入力項目 | 内容 |', '|---|---|']
            for k, v in field_lines(b) + style_lines(b):
                L.append(f"| {k} | {v.replace(chr(10), '<br>').replace('|', '／') or '（空欄）'} |")
            il = image_lines(b, scale)
            if il:
                L += ['', '| 画像 | ファイル | サイズ |', '|---|---|---|']
                L += [f'| {a} | {f} | {s} |' for a, f, s in il]
            L.append('')
    L += ['## OGP画像', '', '- Figma の「OGP画像」（1200×630px）を仕上げて PNG で書き出し、各ページのページ設定「OGP画像」に入れる',
          '- LINE などでシェアしたときの見え方は「LINEでの見え方」を参照（イメージ。実際の見え方はアプリ・端末で変わる）',
          '- 推奨サイズは一般的な OGP の 1200×630px で作っている。invy 側の推奨サイズは要確認', '']
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
:root{--bg:#EEF0F2;--panel:#FFFFFF;--ink:#1C1E22;--muted:#767C83;--line:#D9DDE1;--accent:#D8232A;
  --keep:#767C83;--mod:#D8232A;--new:#2F7367;--shadow:0 14px 40px rgba(28,30,34,.14);}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15171A;--panel:#1F2226;--ink:#EEF0F2;
  --muted:#A2A8AE;--line:#33373C;--accent:#F0666B;--keep:#A2A8AE;--mod:#F0666B;--new:#63A99B;--shadow:0 14px 40px rgba(0,0,0,.5);}}
:root[data-theme="dark"]{--bg:#15171A;--panel:#1F2226;--ink:#EEF0F2;--muted:#A2A8AE;--line:#33373C;--accent:#F0666B;
  --keep:#A2A8AE;--mod:#F0666B;--new:#63A99B;--shadow:0 14px 40px rgba(0,0,0,.5);}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.7 'Noto Sans JP',system-ui,sans-serif;font-feature-settings:"palt" 1}
.wrap{max-width:1400px;margin:0 auto;padding:28px 16px 80px}
header h1{font-size:22px;margin:0 0 4px;letter-spacing:.01em} .sub{color:var(--muted);font-size:12.5px}
.bar{width:48px;height:4px;background:var(--accent);border-radius:2px;margin:14px 0 0}
.board{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:28px;margin-top:28px;align-items:start}
.col h2{font-size:14px;margin:0 0 10px;text-align:center} .col h2 span{color:var(--accent);margin-right:6px;font-family:ui-monospace,monospace}
.col .cap{font-size:11.5px;color:var(--muted);text-align:center;margin-top:8px;line-height:1.6}
.art{background:#fff;border-radius:14px;overflow:hidden;box-shadow:var(--shadow)}
.art svg{display:block;width:100%;height:auto}
.stack{display:flex;flex-direction:column;gap:28px}
.warn{margin-top:22px;padding:12px 16px;border-left:3px solid var(--accent);background:var(--panel);font-size:12.5px;border-radius:0 8px 8px 0}
.tables{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px;margin-top:40px}
.tables h3{font-size:14px;margin:0 0 8px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:12.5px}
th,td{text-align:left;padding:8px 10px;border-top:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:700;border-top:0}
.no{font-family:ui-monospace,monospace;color:var(--muted);white-space:nowrap}
.cls{font-family:ui-monospace,monospace;font-size:10.5px;color:var(--muted);word-break:break-all}
.st{font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}
.st.keep{color:var(--keep)} .st.mod{color:var(--mod)} .st.new{color:var(--new)} .st.plain{color:var(--muted)}
@media (max-width:1100px){.board{grid-template-columns:repeat(2,minmax(0,1fr))}.tables{grid-template-columns:1fr}}
@media (max-width:640px){.board{grid-template-columns:1fr}}
"""


def _inline(svg):
    return svg.split('?>', 1)[-1]


def preview_html(spec, arts, warns):
    """arts = [(番号, 見出し, 補足, svg)]。デザインを横に並べ、下に構成表を置く"""
    proj = html.escape(spec.get('project', '構成案'))
    P = [f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
         f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{proj} 紹介LP</title>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&display=swap">'
         f'<style>{PREVIEW_CSS}</style></head><body><div class="wrap">',
         f'<header><h1>{proj}：紹介LPデザイン案</h1><div class="sub">生成 {datetime.datetime.now():%Y-%m-%d %H:%M}'
         f'／ページは実機375pt幅（Figma用SVGは幅{round(375 * spec.get("_scale", 3))}px）</div><div class="bar"></div></header>']
    if warns:
        P.append('<div class="warn"><b>未確定・要確認</b><br>' + '<br>'.join(html.escape(w) for w in warns) + '</div>')
    pages = [a for a in arts if a[4] == 'page']
    extras = [a for a in arts if a[4] != 'page']
    P.append('<div class="board">')
    for no, title, cap, svg, _ in pages:
        P.append(f'<div class="col"><h2><span>{no}</span>{html.escape(title)}</h2><div class="art">{_inline(svg)}</div>'
                 f'<div class="cap">{html.escape(cap)}</div></div>')
    for no, title, cap, svg, _ in extras:
        P.append(f'<div class="col"><h2><span>{no}</span>{html.escape(title)}</h2><div class="art">{_inline(svg)}</div>'
                 f'<div class="cap">{html.escape(cap)}</div></div>')
    P.append('</div><div class="tables">')
    for p in spec['pages']:
        rows = ''.join(
            f'<tr><td class="no">{j + 1:02d}</td><td>{html.escape(BLOCKS[b["type"]]["label"])}'
            f'<div class="cls">invyBlockEditor-{BLOCKS[b["type"]]["cms"][0]}</div></td>'
            f'<td><span class="st {b["state"]}">{b["state"].upper() if b["state"] != "plain" else "—"}</span></td>'
            f'<td>{html.escape(b.get("note") or "")}</td></tr>' for j, b in enumerate(p['blocks']))
        P.append(f'<div><h3>{PAGE_LABEL[p["pageType"]]}の構成（CMSパーツ）</h3><table><thead><tr><th>No</th>'
                 f'<th>CMSパーツ</th><th>状態</th><th>意図</th></tr></thead><tbody>{rows}</tbody></table></div>')
    P.append('</div></div></body></html>')
    return ''.join(P)


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
    files, arts, boards, sizes = [], [], [], []

    def emit(name, groups, w, h):
        svg = svg_doc(groups, w, h, scale)
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
            f.write(svg)
        files.append(name)
        return svg

    no = 0
    for p in spec['pages']:
        groups, w, h, rwarn, _ = render_page(p, spec, scale, base)
        warns += [f"{PAGE_LABEL[p['pageType']]}: {m}" for m in rwarn]
        label = PAGE_LABEL[p['pageType']]
        svg = emit(f'{proj}_{label}_figma.svg', groups, w, h)
        no += 1
        arts.append((f'{no:02d}', label, f'{len(p["blocks"])}ブロック／{round(w * scale)}×{round(h * scale)}px', svg, 'page'))
        boards.append((label, groups, w, h)); sizes.append((label, w, h))
    g, w, h, _ = render_ogp(spec, scale, base)
    no += 1
    svg = emit(f'{proj}_OGP_figma.svg', g, w, h)
    arts.append((f'{no:02d}', 'OGP画像', f'{round(w * scale)}×{round(h * scale)}px。ページ設定の「OGP画像」にPNGで入れる', svg, 'ogp'))
    boards.append(('OGP画像', g, w, h))
    if any(p['pageType'] == 'inviter' for p in spec['pages']):
        g, w, h, _ = render_line(spec, scale, base)
        no += 1
        svg = emit(f'{proj}_LINE表示イメージ_figma.svg', g, w, h)
        arts.append((f'{no:02d}', 'LINEでの見え方', '紹介フォームの初期メッセージとOGPが、受け取った側にこう届く（イメージ）',
                     svg, 'line'))
        boards.append(('LINEでの見え方', g, w, h))
    # 全部を横に並べた1枚（Figma にまとめて取り込む用）
    GAP, x, allg = 80, 0, []
    for label, groups, w, h in boards:
        allg.append(f'<g id="{label}" transform="translate({round(x * scale)},0)">')
        allg += groups
        allg.append('</g>')
        x += w + GAP
    emit(f'{proj}_figma_all.svg', allg, x - GAP, max(b[3] for b in boards))
    for name, body in ((f'{proj}_cms_sheet.md', sheet_md(spec, scale)), (f'{proj}_cms_sheet.csv', sheet_csv(spec, scale)),
                       (f'{proj}_preview.html', preview_html(spec, arts, warns))):
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
    for label, w, h in sizes:
        print(f'  {label}: {round(w * scale)}×{round(h * scale)}px')
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
