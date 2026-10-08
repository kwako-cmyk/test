# ブロック庫の書き方（HTML ブロックとメタ情報）

Figma「テンプレート」ページ（fileKey `1UwJ64MnV8cHs9F39pSAeH`）の各バリエーションを、1つずつ
HTML ブロック＋メタ情報 JSON に起こしたもの。ブロック一覧は `blocks/inventory.json`。
見本：`blocks/html/benefits-b.html`、`blocks/meta/benefits-b.json`。

## ファイル

| ファイル | 中身 |
|---|---|
| `blocks/html/<id>.html` | HTML 断片。`<section class="blk" data-block="<id>" ...>` 1つだけ |
| `blocks/meta/<id>.json` | 編集できる項目・画像枠・繰り返し・色の役割など |
| `blocks/shots/<id>.png` | Figma のスクリーンショット（見た目の正） |
| `blocks/_base.css` | 全ブロック共通 CSS（色・フォント・テキストスタイル・画像枠・ボタン） |

## HTML のルール

1. ルート：`<section class="blk" data-block="<id>" data-figma="<nodeId>" data-section="<セクション名>" data-variant="<バリエーション名>">`
2. スタイルはブロック内の `<style>` に書き、セレクタは必ず `[data-block="<id>"]` で始める（他ブロックに漏らさない）
3. **色**：Figma で Main 色が当たっている所は `var(--main)`、Sub は `var(--sub)`。それ以外の色は `_base.css` の変数
   （`--fg` `--fg-subtle` `--fg-inactive` `--fg-inverted` `--border` `--bg` `--bg-subtle` `--attention*` `--placeholder`）を使う。
   変数で表せない色だけ直書きしてよい（メタの notes に理由を書く）
4. **文字**：Figma のテキストスタイルに対応するクラスを使う
   `t-headline-lg/md/sm/xs` `t-body-lg/md` `t-caption-md` `t-label-lg/md/md-r`。
   font-family は書かない（`_base.css` の `--font` を継承。日本語 Noto Sans JP / Noto Serif JP、英数 Roboto）
5. **編集できるテキスト**：`data-field="<key>"`。繰り返しの中は `items.<key>` のようにドット区切り
6. **画像枠**：`<div class="img-slot" data-slot="<key>" data-size="<幅>x<高さ>">ラベル</div>`。
   Figma の枠に「270*180」などの表記があればその値、無ければ枠の実寸（px）を data-size に入れる
7. **リンク先**：`<a>` に `data-href-field="<key>"`（文言は中の要素に `data-field`）。メタの fields には `kind: "url"` で載せる
8. **繰り返し**：親に `data-repeat="<key>"`、子に `data-item`。テンプレートにある個数ぶん並べる
9. **アイコン・アバター・挿絵など Figma の素材**：ダウンロードできないので、同じ大きさの枠で代用し
   `data-asset="<Figma のコンポーネント名や layer 名>"` を付ける（例：`var_avatar`、`icon/arrow_chev_right`）。
   簡単な矢印・プラス・閉じるなどは CSS で描いてよい
10. ヘッダー／フローティングバナー／フッター／モーダルのように、Figma で 375×636 のスマホ枠の中に置かれているものは、
   **バーやパネル本体だけ**を起こす（スマホ枠・背景のダミーは入れない）。固定位置はメタの `position` に書く（`top` / `bottom` / `overlay`）
11. レイアウトは flex / grid で組む。absolute 指定は Figma で重ねている所だけ
12. 文言はテンプレートのダミー文言をそのまま入れる

## メタ JSON のルール

```json
{
  "id": "", "section": "", "variant": "", "figmaNode": "", "size": [375, 0],
  "summary": "どんなブロックか1〜2文（構成案を組むときに読む）",
  "position": "flow | top | bottom | overlay",
  "fields":  [{"key": "", "label": "", "kind": "text | richtext | url | number", "example": ""}],
  "images":  [{"slot": "", "label": "", "size": "幅x高さ", "note": ""}],
  "repeats": [{"key": "", "label": "", "templateCount": 0}],
  "assets":  [{"name": "", "note": ""}],
  "colorRoles": {"main": ["Main 色が当たる要素"], "sub": ["Sub 色が当たる要素"]},
  "notes": ""
}
```

- 制約（最小・最大の個数、文字数など）は**書かない**。制約はスプレッドシート側で人が埋める
- `figmaNode` はテンプレートのバリエーションのノード ID（Figma への書き出し時に、このノードを複製する）
