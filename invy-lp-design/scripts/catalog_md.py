#!/usr/bin/env python3
"""blocks/meta.json から blocks/CATALOG.md（ブロック一覧）を作る。

  python3 scripts/catalog_md.py > blocks/CATALOG.md

ブロックを足したり、メタ情報を直したりしたら必ず再生成する。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, 'blocks')
POS = {'top': '上部固定', 'bottom': '下部固定', 'overlay': '重ねて表示', 'flow': ''}


def main():
    inv = json.load(open(os.path.join(B, 'inventory.json'), encoding='utf-8'))
    L = ['# ブロック一覧（CMS テンプレート）', '',
         '> `scripts/catalog_md.py` で生成。直接直さず、`blocks/meta.json` を直して再生成する。', '',
         f"出典：Figma fileKey `{inv['fileKey']}`「テンプレート」ページ。全 {len(inv['variants'])} バリエーション。",
         '見た目は `blocks/shots/<ID>.png`、構造は `blocks/html/<ID>.html`。制約（個数・文字数）は CMS 制約表を見る。', '']
    metas = json.load(open(os.path.join(B, 'meta.json'), encoding='utf-8'))
    sections = []
    for v in inv['variants']:
        if v['section'] not in sections:
            sections.append(v['section'])
    missing = []
    for sec in sections:
        L += [f'## {sec}', '']
        for v in [x for x in inv['variants'] if x['section'] == sec]:
            m = metas.get(v['id'])
            if m is None:
                missing.append(v['id']); L += [f"### `{v['id']}`　{v['name']}（未作成）", '']; continue
            pos = POS.get(m.get('position', 'flow'), '')
            L.append(f"### `{v['id']}`　{v['name']}" + (f"（{pos}）" if pos else ''))
            if m.get('summary'):
                L.append(m['summary'])
            outer = [f for f in m.get('fields', []) if '.' not in f['key']]
            if outer:
                L.append('- 項目：' + '、'.join(f"`{f['key']}` {f['label']}" for f in outer))
            for r in m.get('repeats', []):
                inner = [f for f in m.get('fields', []) if f['key'].startswith(r['key'] + '.')]
                imgs = [i for i in m.get('images', []) if i['slot'].startswith(r['key'] + '.')]
                parts = [f"`{f['key'].split('.', 1)[1]}` {f['label']}" for f in inner]
                parts += [f"`{i['slot'].split('.', 1)[1]}` 画像 {i['size']}" for i in imgs]
                L.append(f"- 繰り返し `{r['key']}`（{r['label']}、テンプレート {r['templateCount']}個）：" + '、'.join(parts))
            top_imgs = [i for i in m.get('images', []) if '.' not in i['slot']]
            if top_imgs:
                L.append('- 画像：' + '、'.join(f"`{i['slot']}` {i['label']} {i['size']}" for i in top_imgs))
            roles = m.get('colorRoles') or {}
            if roles.get('main') or roles.get('sub'):
                L.append('- 色：' + ' ／ '.join(x for x in (
                    ('Main＝' + '・'.join(roles['main'])) if roles.get('main') else '',
                    ('Sub＝' + '・'.join(roles['sub'])) if roles.get('sub') else '') if x))
            L.append('')
    print('\n'.join(L))
    if missing:
        import sys
        print('未作成のブロック: ' + ', '.join(missing), file=sys.stderr)


if __name__ == '__main__':
    main()
