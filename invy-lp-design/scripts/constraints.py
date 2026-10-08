#!/usr/bin/env python3
"""CMS 制約表（Google スプレッドシート）とブロック庫をつなぐ。

  python3 scripts/constraints.py template > 制約表.csv
      ブロック庫のメタ情報から、制約欄が空の表を作る（スプレッドシートの初期化・行の追加用）
  python3 scripts/constraints.py load <スプレッドシートを書き出した.csv> > constraints.json
      人が埋めた制約表を、compose.py --constraints で読める JSON にする

表の列（この順番・この見出しで固定。列を足すときは右端に足す）
  ブロックID / セクション / バリエーション / 区分 / 項目キー / 項目名 / テンプレートの例・サイズ /
  必須 / 最小個数 / 最大個数 / 最大文字数 / 推奨画像サイズ / 使えるページ / 備考
区分：ブロック（ブロック全体の制約）／テキスト／リンク／画像／繰り返し
"""
import csv, io, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLS = ['ブロックID', 'セクション', 'バリエーション', '区分', '項目キー', '項目名', 'テンプレートの例・サイズ',
        '必須', '最小個数', '最大個数', '最大文字数', '推奨画像サイズ', '使えるページ', '備考']


def template():
    inv = json.load(open(os.path.join(ROOT, 'blocks', 'inventory.json'), encoding='utf-8'))
    out = io.StringIO(); w = csv.writer(out); w.writerow(COLS)
    metas = json.load(open(os.path.join(ROOT, 'blocks', 'meta.json'), encoding='utf-8'))
    for v in inv['variants']:
        m = metas.get(v['id'], {})
        base = [v['id'], v['section'], v['name']]
        w.writerow(base + ['ブロック', '', 'ブロック全体', f"{v['w']}x{v['h']}"] + [''] * 7)
        for r in m.get('repeats', []):
            w.writerow(base + ['繰り返し', r['key'], r['label'], f"テンプレート {r['templateCount']}個"] + [''] * 7)
        for f in m.get('fields', []):
            kind = 'リンク' if f.get('kind') == 'url' else 'テキスト'
            ex = str(f.get('example', '')).replace('\n', ' ')[:20]
            w.writerow(base + [kind, f['key'], f['label'], ex] + [''] * 7)
        for im in m.get('images', []):
            w.writerow(base + ['画像', im['slot'], im['label'], im['size']] + [''] * 7)
    return out.getvalue()


def load(path):
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    res = {}
    num = lambda s: int(str(s).strip()) if str(s).strip().isdigit() else None
    for r in rows:
        bid, key = (r.get('ブロックID') or '').strip(), (r.get('項目キー') or '').strip()
        if not bid:
            continue
        rule = {}
        if (r.get('必須') or '').strip() in ('○', '◯', 'TRUE', 'true', '必須', 'はい', 'yes', '1'):
            rule['required'] = True
        for col, k in (('最小個数', 'min'), ('最大個数', 'max'), ('最大文字数', 'maxChars')):
            n = num(r.get(col, ''))
            if n is not None:
                rule[k] = n
        for col, k in (('推奨画像サイズ', 'imageSize'), ('使えるページ', 'pages'), ('備考', 'note')):
            if (r.get(col) or '').strip():
                rule[k] = r[col].strip()
        if rule:
            res.setdefault(bid, {})[key or '_block'] = rule
    return res


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == 'template':
        sys.stdout.write(template())
    elif len(sys.argv) >= 3 and sys.argv[1] == 'load':
        print(json.dumps(load(sys.argv[2]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
