#!/usr/bin/env python3
"""標準構成の spec.json を作る（壁打ちの叩き台）。

使い方:
  python3 scripts/new_spec.py <出力.json> --project "案件名" [--pages inviter,guest] [--brand "#E4007F"]
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog import TEMPLATE, BLOCKS  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('--project', default='案件名')
ap.add_argument('--pages', default='inviter,guest')
ap.add_argument('--brand', help='ブランド配色にする場合の基調色（例 #E4007F）')
a = ap.parse_args()

spec = {
    'project': a.project,
    'theme': {'mode': 'brand', 'primary': a.brand} if a.brand else {'mode': 'wire'},
    'offer': {'inviter': '', 'guest': ''},
    'pages': [],
    'outOfCms': [],
}
for pt in a.pages.split(','):
    pt = pt.strip()
    spec['pages'].append({'pageType': pt, 'title': a.project,
                          'blocks': [{'type': t, 'state': 'new', 'note': '', 'data': {}} for t in TEMPLATE[pt]]})
with open(a.out, 'w', encoding='utf-8') as f:
    json.dump(spec, f, ensure_ascii=False, indent=2)
print('作成:', a.out)
for p in spec['pages']:
    print(' ', p['pageType'], ' → '.join(BLOCKS[b['type']]['label'] for b in p['blocks']))
