#!/usr/bin/env python3
"""標準構成の spec.json を作る（壁打ちの叩き台）。

使い方:
  python3 scripts/new_spec.py <出力.json> --project "案件名" [--slug client] [--pages inviter,guest]
                               [--primary "#D9546E"] [--secondary "#2F5D62"]
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog import TEMPLATE, BLOCKS  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('--project', default='案件名')
ap.add_argument('--pages', default='inviter,guest')
ap.add_argument('--slug', default='client', help='invy の URL のクライアント部分')
ap.add_argument('--primary', help='CTA などの色（省略時は既定の配色）')
ap.add_argument('--secondary', help='ヒーロー・リボンの色（省略時は既定の配色）')
a = ap.parse_args()

spec = {
    'project': a.project,
    'slug': a.slug,
    'theme': {k: v for k, v in (('mode', 'brand'), ('primary', a.primary), ('secondary', a.secondary)) if v},
    'offer': {'inviter': '', 'guest': ''},
    'pages': [],
    'outOfCms': [],
}
for pt in a.pages.split(','):
    pt = pt.strip()
    spec['pages'].append({'pageType': pt, 'title': a.project, 'settings': {'description': '', 'ogp': ''},
                          'blocks': [{'type': t, 'state': 'new', 'note': '', 'data': {}} for t in TEMPLATE[pt]]})
with open(a.out, 'w', encoding='utf-8') as f:
    json.dump(spec, f, ensure_ascii=False, indent=2)
print('作成:', a.out)
for p in spec['pages']:
    print(' ', p['pageType'], ' → '.join(BLOCKS[b['type']]['label'] for b in p['blocks']))
