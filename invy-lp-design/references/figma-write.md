# Figma への書き出し（コネクタで直接書き込む）

テンプレートファイル（fileKey `1UwJ64MnV8cHs9F39pSAeH`）の中に**案件ごとのページを新しく作り**、
テンプレートのバリエーションを**複製して**縦に並べる。テンプレート本体（「テンプレート」ページ）と、
色スタイル Main / Sub は**書き換えない**。

事前に必ず：Figma のスキル `figma-use` と `figma-generate-design` を読む（`get_figma_skill` で
`skill://figma/figma-use/SKILL.md`、`skill://figma/figma-generate-design/SKILL.md`）。
`use_figma` には毎回 `skillNames: "resource:figma-use,resource:figma-generate-design"` を付ける。

**接続がない・切れているとき**：Figma コネクタが使えない場合は書き出しを止め、
「claude.ai のコネクタ設定で Figma を再接続してください」と伝える。HTML（compose.py の出力）までは先に渡してよい。

## 動作確認済みの範囲（2026-10 時点）

| 手順 | 状態 |
|---|---|
| 1. ページと外枠を作る | 確認済み |
| 2. バリエーションを複製して並べる（スマホ枠の中身だけ取り出す） | 確認済み |
| 3. Main / Sub の塗りを案件の色に差し替える | 確認済み |
| 4. フォントのモードを外枠に当てる | 確認済み |
| 5. 文言を書き換える | 1か所で確認済み。全文の対応付けは手順どおりに行う |
| 6. 繰り返しの個数を合わせる | 未確認 |
| 7. 画像を入れる（upload_assets → imageHash） | 未確認 |

未確認の手順で失敗したら、その部分は Figma 上で手作業にしてもらうよう伝え、HTML 側の内容を渡す。

## 手順 1〜4：組み立て（1回の use_figma）

`BLOCKS` には page.json の各ブロックの `figmaNode`（`blocks/inventory.json` で引く）を順に入れる。

```js
const BLOCKS = ['3119:13112', '3119:13173', '3119:14125'];   // page.json のブロック順
const PAGE_NAME = '【案件名】2026-10-08';
const FRAME_NAME = '紹介者ページ';
const MAIN = '#0068B7', SUB = '#E60012';
const FONT_MODE = 'ゴシック／標準';   // ゴシック／標準・ゴシック／細め・明朝／標準・明朝／細め

const hex = h => ({ r: parseInt(h.slice(1,3),16)/255, g: parseInt(h.slice(3,5),16)/255, b: parseInt(h.slice(5,7),16)/255 });
let page = figma.root.children.find(p => p.name === PAGE_NAME);
if (!page) { page = figma.createPage(); page.name = PAGE_NAME; }
let x = 0; for (const c of page.children) x = Math.max(x, c.x + c.width + 120);
const wrapper = figma.createAutoLayout('VERTICAL', { name: FRAME_NAME, itemSpacing: 0 });
wrapper.resize(375, 100); wrapper.counterAxisSizingMode = 'FIXED';
wrapper.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 } }];
page.appendChild(wrapper); wrapper.x = x; wrapper.y = 0;

const created = [];
for (const id of BLOCKS) {
  const src = await figma.getNodeByIdAsync(id);
  let target = src;   // ヘッダー・バナー・フッター等は 375x636 のスマホ枠の中に 1つだけ入っている
  if (src.type === 'FRAME' && src.layoutMode === 'NONE' && src.children.length === 1 && Math.round(src.height) === 636) target = src.children[0];
  const c = target.clone();
  wrapper.appendChild(c);
  if ('layoutPositioning' in c) c.layoutPositioning = 'AUTO';
  c.layoutSizingHorizontal = 'FILL';
  created.push({ id: c.id, name: c.name, h: Math.round(c.height) });
}
// 色：Main / Sub スタイルが当たっている塗り・線だけ差し替える（スタイル自体は変えない）
const styles = await figma.getLocalPaintStylesAsync();
const mainId = styles.find(s => s.name === 'Main').id, subId = styles.find(s => s.name === 'Sub').id;
let recolored = 0;
for (const n of wrapper.findAll(() => true)) {
  for (const [prop, sprop] of [['fills', 'fillStyleId'], ['strokes', 'strokeStyleId']]) {
    if (!(sprop in n) || typeof n[sprop] !== 'string') continue;
    if (n[sprop] !== mainId && n[sprop] !== subId) continue;
    const col = hex(n[sprop] === mainId ? MAIN : SUB);
    if (sprop === 'fillStyleId') await n.setFillStyleIdAsync(''); else await n.setStrokeStyleIdAsync('');
    n[prop] = [{ type: 'SOLID', color: col }];
    recolored++;
  }
}
// フォント：typography コレクションのモードを外枠に当てる（子に継承される）
const typo = (await figma.variables.getLocalVariableCollectionsAsync()).find(c => c.name === 'typography');
for (const f of [['Noto Sans JP','Regular'],['Noto Sans JP','Bold'],['Noto Serif JP','Regular'],['Noto Serif JP','Bold']])
  await figma.loadFontAsync({ family: f[0], style: f[1] });
wrapper.setExplicitVariableModeForCollection(typo, typo.modes.find(m => m.name === FONT_MODE).modeId);
return { pageId: page.id, wrapperId: wrapper.id, created, recolored };
```

## 手順 5：文言の書き換え

Figma のテキストと HTML の `data-field` は自動では対応しない。ブロックごとに次の2段で行う。

1. **読む**：複製したブロックの TEXT ノードを一覧にする（id・レイヤー名・文字の先頭30字・y座標）
   ```js
   const blk = await figma.getNodeByIdAsync('複製したブロックのID');
   return blk.findAllWithCriteria({ types: ['TEXT'] }).map(t => ({ id: t.id, name: t.name, text: t.characters.slice(0, 30), y: Math.round(t.absoluteTransform[1][2]) }));
   ```
2. **書く**：page.json の内容と、メタ情報の `example`（テンプレートのダミー文言）を見比べて対応を決め、id 指定で書き換える。
   フォントは必ず現在のフォントを読み込んでから書く
   ```js
   const EDITS = { '10017:3777': 'お友だち紹介で\n2人ともにウレシイ特典' };
   for (const [id, text] of Object.entries(EDITS)) {
     const t = await figma.getNodeByIdAsync(id);
     for (const f of t.getRangeAllFontNames(0, t.characters.length)) await figma.loadFontAsync(f);
     t.characters = text;
   }
   return { edited: Object.keys(EDITS) };
   ```

## 手順 6：繰り返しの個数（未確認）

繰り返し（特典カード、FAQ、スライドなど）は、Figma では同じ名前のフレームが兄弟として並んでいる。
- 減らす：余分なフレームを `remove()`
- 増やす：最後のフレームを `clone()` して同じ親に `appendChild`
- 個数を変えたら、手順 5 の「読む」をやり直してから文言を書く

## 手順 7：画像（未確認）

`use_figma` では外部の画像を直接読み込めない（`createImageAsync` は使えない）。
Figma コネクタの `upload_assets` で画像をアップロードし、返ってきた `imageHash` を
画像枠（グレーの矩形。名前は `image` など）の塗りに入れる：
`node.fills = [{ type: 'IMAGE', imageHash: '<hash>', scaleMode: 'FILL' }]`

## 仕上げ

- 最後に外枠のスクリーンショットを1回撮り、文字の切れ・重なり・色・フォントを確認する
- 作ったページ名と外枠の id を、案件フォルダの `figma.json` に残す（修正のときに使う）
