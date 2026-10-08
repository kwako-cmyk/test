# ページ設計書（page.json）と compose.py

案件フォルダに `page.json` を1つ置く。紹介者ページとゲストページは同じファイルの `pages` に並べる。
記入例：`assets/sample_page.json`

```json
{
  "project": "案件名",
  "theme": {"main": "#0068B7", "sub": "#E60012", "font": "gothic-regular"},
  "pages": [
    {
      "name": "紹介者ページ",
      "blocks": [
        {"block": "header-pill", "fields": {"buttonLabel": "紹介する", "buttonUrl": "#invy-form"},
         "images": {"logo": "assets/logo.png"}},
        {"block": "benefits-a",
         "fields": {"title": "お友だちに\n紹介特典をプレゼント", "note": "特典の条件"},
         "repeats": {"items": [
           {"who": "あなたに", "heading": "QUOカードPay 3,000円分", "text": "説明"},
           {"who": "お友達に", "heading": "初回20%OFF", "text": "説明"}
         ]},
         "note": "このブロックで伝える1点（構成表に出る）"}
      ]
    }
  ]
}
```

| キー | 内容 |
|---|---|
| `block` | ブロック ID（`blocks/CATALOG.md`） |
| `fields` | 入力項目。キーはメタ情報の `fields[].key`（繰り返しの外側のもの）。改行は `\n` |
| `repeats` | 繰り返し。キーは `repeats[].key`。中身は項目キーの `.` より後ろ（`items.who` → `who`）。並べた数がそのまま個数になる |
| `images` | 画像枠 → 画像ファイル（page.json からの相対パス）。繰り返しの中の画像は `repeats` の各要素に書く（`items.image` → `"image": "..."`） |
| `note` | このブロックで伝える1点 |
| `theme.font` | `gothic-regular` / `gothic-light` / `mincho-regular` / `mincho-light`（Figma の typography モードと同じ） |

## compose.py

```bash
python3 scripts/compose.py <page.json> --wire --constraints <constraints.json>   # 構成案（グレースケール）
python3 scripts/compose.py <page.json> --constraints <constraints.json>          # デザイン
```

- 出力：`<page.json のフォルダ>/out/<案件>_<ページ名>.html`（CSS と画像を埋め込んだ単体 HTML）
- 警告：存在しない項目、見つからない画像、制約違反（個数・文字数・必須）。**警告をゼロにしてから渡す**
- ブロックの HTML は変えない。見た目を変えたいときは、別のバリエーションを選ぶ
