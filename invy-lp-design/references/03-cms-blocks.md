# invy CMS ブロックカタログ

> `scripts/catalog.py` から生成（`python3 scripts/catalog.py --md > references/03-cms-blocks.md`）。
> ここを直接直さず、`catalog.py` を直して再生成する。

LP はこのカタログのブロックだけで組む。`type` は spec.json に書く値、`CMSクラス` は invy CMS の
`invyBlockEditor-<クラス>`。画像サイズはツール上の既定比率（pt、×3 で px）で、**CMS 側の推奨入稿サイズは要確認**。

| ページ | 意味 |
|---|---|
| both | 紹介者・ゲスト両方 |
| inviter | 紹介者ページのみ |
| guest | ゲストページのみ |

## ヘッダー・KV

### ヘッダー（ロゴ＋ボタン）　`brand-logo`
- ページ：both　／　CMSクラス：`brand-logo`
- 入力項目：`logoPos` ロゴ画像表示位置（left=左寄せ / center=中央）、`ctaOn` 紹介CTA（右上）あり／なし（true / false）、`ctaType` バナー種類（text=テキスト / image=画像）、`cta` ヘッダーボタン文言（リッチテキスト）、`btnShape` ボタンスタイル（round=角丸 / square=四角）、`href` CTAのリンク先（空白なら #invy-form ＝紹介フォームへ移動）
- 画像：`logo` ブランドロゴ画像（140×34pt）、`ctaImg` ヘッダーボタン画像（バナー種類＝画像のとき）（116×36pt）

### キービジュアル（画像）　`kv-image`
- ページ：both　／　CMSクラス：`keyvisual`
- 入力項目：`sub` KV内の小見出し（画像に入れる文言）、`copy` KV内のメインコピー（画像に入れる文言）、`bubble` KV内の吹き出し（特典の訴求。画像に入れる文言）、`alt` 画像の説明（代替テキスト）
- 画像：`kv` KV画像（支給があれば差し替え）（375×500pt）

### キービジュアル（コピー＋画像）　`keyvisual`
- ページ：both　／　CMSクラス：`keyvisual`
- 入力項目：`eyebrow` 小見出し、`title` メインコピー、`lead` リード文、`cta` ボタン文言
- 画像：`kv` KVメイン画像（335×250pt）

### タイマー表示　`service-show-timer`
- ページ：both　／　CMSクラス：`service-show-timer`
- 入力項目：`title` 見出し、`lead` タイマー表示

## 訴求

### 特典エリア　`benefits`
- ページ：both　／　CMSクラス：`benefits`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`lead` カード内の見出し、`capA` 紹介者ラベル（リボン）、`a` 紹介者特典、`subA` 紹介者特典の補足、`capB` ゲストラベル（リボン）、`b` ゲスト特典、`subB` ゲスト特典の補足、`note` 特典の条件（注記）、`cta` ボタン文言
- 画像：`ico1` 紹介者特典アイコン（50×50pt）、`ico2` ゲスト特典アイコン（50×50pt）

### 見出し　`headline`
- ページ：both　／　CMSクラス：`headline`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し

### テキスト　`text-editor`
- ページ：both　／　CMSクラス：`text-editor`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`lead` 本文

### 画像　`image`
- ページ：both　／　CMSクラス：`image`
- 入力項目：`alt` 画像の説明（代替テキスト）
- 画像：`img` 画像（335×213pt）

### フレーム（枠付き）　`frame`
- ページ：both　／　CMSクラス：`frame`
- 入力項目：`title` 見出し、`lead` 本文
- 画像：`img` フレーム内の画像（311×200pt）

### フレーム（リスト）　`frame-list`
- ページ：both　／　CMSクラス：`frame-list`, `list-frame`
- 入力項目：`title` 見出し、`rows` 項目（チェック付きの箇条書き。画像は任意）、`showImages` 項目ごとの画像枠を出す（true / false）
- 画像：`r{i}` 項目画像（311×140pt）

### 口コミ（ギャラリー）　`review-gallery`
- ページ：both　／　CMSクラス：`review-gallery`, `gallery`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し
- 画像：`g{i}` ギャラリー画像（163×163pt）

### 口コミ（リスト）　`review-list`
- ページ：both　／　CMSクラス：`review`, `reviews`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`rows` 口コミ本文、`cta` もっと見るボタン文言
- 画像：`rv{i}` 口コミ画像（100×80pt）

### 画像スライダー　`image-slider`
- ページ：both　／　CMSクラス：`image-slider`, `KVSlider`
- 入力項目：`slides` スライド
- 画像：`s{i}` スライド画像（224×224pt）

### 画像スライダー（テキスト付き）　`image-slider-text`
- ページ：both　／　CMSクラス：`image-slider-text`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`slides` スライド（画像＋説明文＋任意ボタン）
- 画像：`s{i}` スライド画像（224×160pt）

### クーポンメッセージ　`coupon-message`
- ページ：guest　／　CMSクラス：`coupon-message`
- 入力項目：`title` 見出し、`lead` 本文

### サービス紹介エリア　`service-introduction`
- ページ：guest　／　CMSクラス：`service-introduction`
- 入力項目：`title` 見出し、`lead` 本文

### おすすめシェア文　`service-show-recommend`
- ページ：inviter　／　CMSクラス：`service-show-recommend`
- 入力項目：`title` 見出し、`lead` シェア文

## 説明

### 紹介上手になるためのヒント　`hint`
- ページ：inviter　／　CMSクラス：`hint`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`slides` ヒント（画像＋説明文）
- 画像：`s{i}` ヒント画像（224×160pt）

### 紹介方法（紹介の流れ）　`flow`
- ページ：both　／　CMSクラス：`flow`, `flow2`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`steps` ステップ（画像＋説明）、`showImages` ステップ画像の枠を出す（true / false）
- 画像：`st{i}` ステップ画像（272×120pt）

### 紹介方法（タブ）　`flow-tab`
- ページ：both　／　CMSクラス：`flow-tab`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`t1` タブ1、`t2` タブ2、`steps` ステップ

### ご紹介方法の詳細　`invitation-detail`
- ページ：inviter　／　CMSクラス：`invitation-detail`
- 入力項目：`title` 見出し、`items` 項目（見出し＋開いた中身）

### よくあるご質問　`faq`
- ページ：both　／　CMSクラス：`faq`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`items` Q&A

### アコーディオンリスト　`accordion-list`
- ページ：both　／　CMSクラス：`accordion-list`
- 入力項目：`title` 見出し、`items` 項目

### YouTube埋め込み　`youtube`
- ページ：both　／　CMSクラス：`youtube`, `video`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`url` 動画URL
- 画像：`thumb` サムネイル（335×188pt）

### モーダル表示　`modal`
- ページ：both　／　CMSクラス：`show-modal`, `modal`
- 入力項目：`title` 見出し、`lead` 本文、`cta` 閉じるボタン文言

## アクション

### CTA（ボタン）　`button`
- ページ：both　／　CMSクラス：`cta`
- 入力項目：`label` ボタン文言、`href` 遷移先、`measure` 計測方法

### 紹介フォーム　`invite-form`
- ページ：inviter　／　CMSクラス：`invite-form`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`f1` 項目1、`f2` 項目2、`f3` メッセージ欄の見出し、`msg` 初期メッセージ（送信文テンプレート）、`cta` LINEボタン文言

### ゲストフォーム　`guest-form`
- ページ：guest　／　CMSクラス：`guest-form`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`f1` 項目1、`f2` 項目2、`cta` 送信ボタン文言

### クーポンコード　`invitation-code`
- ページ：guest　／　CMSクラス：`invitation-code`, `coupon-code`
- 入力項目：`eyebrow` 見出しラベル（英字）、`title` 見出し、`lead` 説明、`code` コード表示、`cta` コピーボタン文言

### クライアントサイトのリンク　`client-site-link`
- ページ：both　／　CMSクラス：`client-site-link`
- 入力項目：`title` 見出し、`cta` ボタン文言、`fine` ボタン下の注記、`href` 遷移先、`measure` 計測方法

### 来店計測へのリンク　`coming-form-link`
- ページ：guest　／　CMSクラス：`coming-form-link`, `client-site-coming-form-link`
- 入力項目：`title` 見出し、`cta` ボタン文言、`fine` ボタン下の注記

## 規約・フッター

### 必ずお読みください　`please-read`
- ページ：both　／　CMSクラス：`please-read-text-editor`, `please-read-text-editor2`
- 入力項目：`title` 見出し、`bullets` 箇条書き

### 注意点などの箇条書きリスト　`notice-list`
- ページ：both　／　CMSクラス：`notice-list`, `attention-list`
- 入力項目：`title` 見出し、`bullets` 箇条書き

### フッター（規約リンク）　`footer`
- ページ：both　／　CMSクラス：`footer`
- 入力項目：`name` 表示名、`a` リンク1、`b` リンク2

### フローティングバナー　`invitation-banner`
- ページ：both　／　CMSクラス：`invitation-banner`, `guest-banner`, `floating-banner-with-timer`, `floating-banner-with-timer2`
- 入力項目：`cta` バナー文言

## 全コンポーネント共通の設定

| spec のキー | CMS の項目 | メモ |
|---|---|---|
| `id` | コンポーネントのID | ページ内リンクの飛び先に使える（CTA のリンク先に #ID を書く） |
| `label` | コンポーネントのラベル | 管理用の名前 |
| `hidden` | 非表示にする | 一時的に隠す |
| `style.border` | スタイル設定：枠線で囲う | true / false |
| `style.bg` | スタイル設定：背景色 | カラーコード。style.bgOpacity で透明度（0〜100%） |
| `style.padding` | スタイル設定：余白（全体） | px |

リッチテキスト欄で指定できるもの：H1〜H6、太字・斜体・取り消し線・下線、画像、リンク、箇条書き・番号付き、左右中央揃え、フォント、サイズ、文字色、背景色

## ページ全体の設定

| spec のキー（pageSettings） | CMS の項目 | メモ |
|---|---|---|
| `theme` | テーマ選択 | 例：ゴシック／フォント標準。ページ全体のフォントが決まる |
| `title` | ページのタイトル | 必須 |
| `description` | ページのdescription | 必須 |
| `ogp` | OGP画像 | 必須。シェア時に表示される画像 |
| `bgImage` | 背景画像 | ページの背景画像（表示のされ方は要確認） |
| `headScript` | スクリプト（head）に挿入 | ボタン色などの CSS 調整もここに入れる |
| `bodyScript` | スクリプト（</body>の直前）に挿入 | 任意のスクリプト |
| `threeStepForm` | 3ステップフォームを使用する | ON / OFF（挙動は要確認） |
| `index` | インデックスを許可する | 有効 / 無効 |

## 色の変え方（CMS 上の手段）

| 変えたいもの | CMS でのやり方 |
|---|---|
| 背景色 | 各コンポーネントの「スタイル設定」→ 背景色・透明度 |
| 文字色・文字の背景色 | リッチテキスト欄の「文字色」「背景色」 |
| ボタンの形 | ヘッダーは「ボタンスタイル」で角丸／四角を選択（他コンポーネントは要確認） |
| ボタンの色 | ページ設定の「スクリプト（head）に挿入」に CSS を書く。確認済みのクラス：`.formBtn--mailto`（紹介フォームの「メールで送る」）。他のボタンのクラス名は要確認 |
| KV・装飾の多い見出し | 画像で作って画像コンポーネントに入れる（CMS の部品で色や装飾を作り込まない） |

ここに無い手段で色を当てたデザインは、CMS で再現できない前提で扱う。

## カタログ外（CMSにはあるが、このスキルでは使わない）

- `table`：表
- `video`：ビデオ（YouTube埋め込みで代替）
- `pdf`：PDFファイル
- `download-button`：ダウンロードボタン

## 新規作成時の標準構成

- 紹介者ページ：ヘッダー（ロゴ＋ボタン） → キービジュアル（画像） → 特典エリア → 紹介方法（紹介の流れ） → 紹介上手になるためのヒント → 紹介フォーム → ご紹介方法の詳細 → よくあるご質問 → 必ずお読みください → 注意点などの箇条書きリスト → フッター（規約リンク） → フローティングバナー
- ゲストページ：ヘッダー（ロゴ＋ボタン） → キービジュアル（画像） → クーポンメッセージ → 特典エリア → 紹介方法（紹介の流れ） → ゲストフォーム → クーポンコード → よくあるご質問 → 必ずお読みください → 注意点などの箇条書きリスト → フッター（規約リンク） → フローティングバナー
