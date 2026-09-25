"""invy CMS のブロック（テンプレートパーツ）カタログ。

LP の構成は、ここに定義されたブロックだけで組む。ここに無いものは CMS で作れない前提で扱い、
勝手に足さない（必要なら「CMS外の要望」として別に書き出す）。

- 出典：invy CMS の `invyBlockEditor-*` クラスと、Figma「パルクローゼット様」テンプレートページ
- 数値は実機 375pt 幅の pt 単位。書き出し時に scale（既定 3）を掛けて 1125px にする

`python3 catalog.py --md` で references/03-cms-blocks.md を再生成できる。
"""
import copy, json, sys

CATS = ['ヘッダー・KV', '訴求', '説明', 'アクション', '規約・フッター']

# fields: (key, 表示名, kind)  kind = text | multi | list | items | slides
# images: (slot, 表示名, w, h)  w/h は pt（ツール上の既定比率。CMS側の推奨サイズは要確認）
BLOCKS = {
  'brand-logo': dict(label='ヘッダー（ロゴ＋ボタン）', cat='ヘッダー・KV', page='both', cms=['brand-logo'],
    fields=[('logoPos', 'ロゴ画像表示位置（left=左寄せ / center=中央）', 'text'),
            ('ctaOn', '紹介CTA（右上）あり／なし（true / false）', 'text'),
            ('ctaType', 'バナー種類（text=テキスト / image=画像）', 'text'),
            ('cta', 'ヘッダーボタン文言（リッチテキスト）', 'text'),
            ('btnShape', 'ボタンスタイル（round=角丸 / square=四角）', 'text'),
            ('href', 'CTAのリンク先（空白なら #invy-form ＝紹介フォームへ移動）', 'text')],
    images=[('logo', 'ブランドロゴ画像', 140, 34), ('ctaImg', 'ヘッダーボタン画像（バナー種類＝画像のとき）', 116, 36)],
    data={'logoPos': 'left', 'ctaOn': True, 'ctaType': 'text', 'cta': 'クーポンをシェア', 'btnShape': 'round', 'href': ''}),
  'kv-image': dict(label='キービジュアル（画像）', cat='ヘッダー・KV', page='both', cms=['keyvisual'],
    fields=[('sub', 'KV内の小見出し（画像に入れる文言）', 'text'), ('copy', 'KV内のメインコピー（画像に入れる文言）', 'multi'),
            ('bubble', 'KV内の吹き出し（特典の訴求。画像に入れる文言）', 'multi'), ('alt', '画像の説明（代替テキスト）', 'text')],
    images=[('kv', 'KV画像（完成画像が支給されたとき。これ1枚で置き換える）', 375, 500),
            ('photo', 'KV内の写真（色面のヒーローの中に入れる写真）', 375, 327)],
    data={'sub': 'お友だち紹介キャンペーン', 'copy': 'ご紹介で\nおふたりに特典を', 'bubble': 'おふたりに\n特典プレゼント',
          'alt': 'お友だち紹介キャンペーン'}),
  'keyvisual': dict(label='キービジュアル（コピー＋画像）', cat='ヘッダー・KV', page='both', cms=['keyvisual'],
    fields=[('eyebrow', '小見出し', 'text'), ('title', 'メインコピー', 'multi'), ('lead', 'リード文', 'multi'),
            ('cta', 'ボタン文言', 'text')],
    images=[('kv', 'KVメイン画像', 335, 250)],
    data={'eyebrow': 'お友だち紹介キャンペーン', 'title': '紹介するほど、\nふたりとも嬉しい。',
          'lead': 'お友だちを紹介すると、あなたにもお友だちにも特典をプレゼント。', 'cta': '友だちを紹介する'}),
  'service-show-timer': dict(label='タイマー表示', cat='ヘッダー・KV', page='both', cms=['service-show-timer'],
    fields=[('title', '見出し', 'text'), ('lead', 'タイマー表示', 'text')],
    data={'title': 'キャンペーン終了まで', 'lead': '残り 00日 00:00:00'}),
  'benefits': dict(label='特典エリア', cat='訴求', page='both', cms=['benefits'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('lead', 'カード内の見出し', 'text'),
            ('capA', '紹介者ラベル（リボン）', 'text'), ('a', '紹介者特典', 'text'), ('subA', '紹介者特典の補足', 'text'),
            ('capB', 'ゲストラベル（リボン）', 'text'), ('b', 'ゲスト特典', 'text'), ('subB', 'ゲスト特典の補足', 'text'),
            ('note', '特典の条件（注記）', 'multi'), ('cta', 'ボタン文言', 'text')],
    images=[('ico1', '紹介者特典アイコン', 50, 50), ('ico2', 'ゲスト特典アイコン', 50, 50)],
    data={'eyebrow': 'PRESENT', 'title': 'ご紹介で、おふたりに\n特典をプレゼント', 'lead': '紹介限定の特典',
          'capA': 'ご紹介くださった方', 'a': '1,000円分クーポン', 'subA': '',
          'capB': 'ご紹介を受けた方', 'b': '初回1,000円OFF', 'subB': '', 'note': '', 'cta': 'お友だちに紹介する'}),
  'headline': dict(label='見出し', cat='訴求', page='both', cms=['headline'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi')], data={'title': '見出しを入力'}),
  'text-editor': dict(label='テキスト', cat='訴求', page='both', cms=['text-editor'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('lead', '本文', 'multi')],
    data={'title': '見出し', 'lead': 'ここに本文が入ります。'}),
  'image': dict(label='画像', cat='訴求', page='both', cms=['image'],
    fields=[('alt', '画像の説明（代替テキスト）', 'text')],
    images=[('img', '画像', 335, 213)], data={'alt': '画像'}),
  'frame': dict(label='フレーム（枠付き）', cat='訴求', page='both', cms=['frame'],
    fields=[('title', '見出し', 'multi'), ('lead', '本文', 'multi')],
    images=[('img', 'フレーム内の画像', 311, 200)],
    data={'title': 'フレーム見出し', 'lead': 'テキストが入りますテキストが入りますテキストが入ります'}),
  'frame-list': dict(label='フレーム（リスト）', cat='訴求', page='both', cms=['frame-list', 'list-frame'],
    fields=[('title', '見出し', 'multi'), ('rows', '項目（チェック付きの箇条書き。画像は任意）', 'list'),
            ('showImages', '項目ごとの画像枠を出す（true / false）', 'text')],
    images=[('r{i}', '項目画像', 311, 140)],
    data={'title': 'ご紹介くださる方が\nすすめるポイント', 'rows': ['ポイントが入ります', 'ポイントが入ります', 'ポイントが入ります'],
          'showImages': False}),
  'review-gallery': dict(label='口コミ（ギャラリー）', cat='訴求', page='both', cms=['review-gallery', 'gallery'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi')],
    images=[('g{i}', 'ギャラリー画像', 163, 163)], data={'title': 'ギャラリー', 'count': 4}),
  'review-list': dict(label='口コミ（リスト）', cat='訴求', page='both', cms=['review', 'reviews'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('rows', '口コミ本文', 'list'), ('cta', 'もっと見るボタン文言', 'text')],
    images=[('rv{i}', '口コミ画像', 100, 80)],
    data={'title': '口コミ', 'rows': ['テキストが入ります'] * 3, 'cta': '口コミをもっと見る'}),
  'image-slider': dict(label='画像スライダー', cat='訴求', page='both', cms=['image-slider', 'KVSlider'],
    fields=[('slides', 'スライド', 'slides')],
    images=[('s{i}', 'スライド画像', 224, 224)], data={'slides': [{'text': ''}, {'text': ''}, {'text': ''}]}),
  'image-slider-text': dict(label='画像スライダー（テキスト付き）', cat='訴求', page='both', cms=['image-slider-text'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('slides', 'スライド（画像＋説明文＋任意ボタン）', 'slides')],
    images=[('s{i}', 'スライド画像', 224, 160)],
    data={'title': 'スライダー見出し',
          'slides': [{'text': 'スライド1の説明文'}, {'text': 'スライド2の説明文'}, {'text': 'スライド3の説明文'}]}),
  'coupon-message': dict(label='クーポンメッセージ', cat='訴求', page='guest', cms=['coupon-message'],
    fields=[('title', '見出し', 'multi'), ('lead', '本文', 'multi')],
    data={'title': 'お友だちからクーポンが届いています', 'lead': ''}),
  'service-introduction': dict(label='サービス紹介エリア', cat='訴求', page='guest', cms=['service-introduction'],
    fields=[('title', '見出し', 'multi'), ('lead', '本文', 'multi')],
    data={'title': 'サービスのご紹介', 'lead': 'サービス説明が入ります。'}),
  'service-show-recommend': dict(label='おすすめシェア文', cat='訴求', page='inviter', cms=['service-show-recommend'],
    fields=[('title', '見出し', 'multi'), ('lead', 'シェア文', 'multi')],
    data={'title': 'おすすめのシェア文', 'lead': 'コピーしてそのまま送れる紹介文です。'}),
  'hint': dict(label='紹介上手になるためのヒント', cat='説明', page='inviter', cms=['hint'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('slides', 'ヒント（画像＋説明文）', 'slides')],
    images=[('s{i}', 'ヒント画像', 224, 160)],
    data={'title': 'こんなシーンで\nご紹介ください', 'slides': [
      {'text': 'LINEグループでのシェアもOK。仲良しの友だちにシェアして広めてみましょう。'},
      {'text': 'URLをコピーしてSNSに投稿できます。フォロワーにシェアして特典をゲット。'},
      {'text': '体験や良かった点を一緒に伝えると効果的です。'}]}),
  'flow': dict(label='紹介方法（紹介の流れ）', cat='説明', page='both', cms=['flow', 'flow2'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('steps', 'ステップ（画像＋説明）', 'list'),
            ('showImages', 'ステップ画像の枠を出す（true / false）', 'text')],
    images=[('st{i}', 'ステップ画像', 272, 120)],
    data={'title': 'ご紹介の流れ', 'steps': ['紹介用のURLをお友だちに送る', 'お友だちがURLから申し込む', 'ふたりに特典が届く']}),
  'flow-tab': dict(label='紹介方法（タブ）', cat='説明', page='both', cms=['flow-tab'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('t1', 'タブ1', 'text'), ('t2', 'タブ2', 'text'), ('steps', 'ステップ', 'list')],
    data={'title': '紹介の流れ', 't1': '紹介する方', 't2': '紹介される方', 'steps': ['STEP1の説明', 'STEP2の説明', 'STEP3の説明']}),
  'invitation-detail': dict(label='ご紹介方法の詳細', cat='説明', page='inviter', cms=['invitation-detail'],
    fields=[('title', '見出し', 'multi'), ('items', '項目（見出し＋開いた中身）', 'items')],
    data={'title': 'ご紹介方法の詳細', 'items': [
      {'q': 'LINEの紹介方法', 'a': '「LINEで送る」をタップするとLINEが起動します。送りたい相手を選んで転送してください。'},
      {'q': 'メールでの紹介方法', 'a': '「メールで送る」をタップするとメーラーが起動します。宛先を選んで送信してください。'},
      {'q': 'リンクでのシェア方法', 'a': 'URLをコピーして、SNSやブログなどお好きな方法でシェアしてください。'}]}),
  'faq': dict(label='よくあるご質問', cat='説明', page='both', cms=['faq'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('items', 'Q&A', 'items')],
    data={'title': 'よくあるご質問', 'items': [
      {'q': '紹介できる人数に上限はありますか？', 'a': '上限はありません。何人でも紹介いただけます。'},
      {'q': '特典はいつ届きますか？', 'a': 'お友だちのご利用が確認できた後に付与されます。'},
      {'q': 'LINE以外でも紹介できますか？', 'a': 'URLをコピーして、メールやSNSでも共有いただけます。'}]}),
  'accordion-list': dict(label='アコーディオンリスト', cat='説明', page='both', cms=['accordion-list'],
    fields=[('title', '見出し', 'multi'), ('items', '項目', 'items')],
    data={'title': 'アコーディオンリスト', 'items': [{'q': '項目1', 'a': ''}, {'q': '項目2', 'a': ''}, {'q': '項目3', 'a': ''}]}),
  'youtube': dict(label='YouTube埋め込み', cat='説明', page='both', cms=['youtube', 'video'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('url', '動画URL', 'text')],
    images=[('thumb', 'サムネイル', 335, 188)], data={'title': '紹介の流れを動画で見る', 'url': ''}),
  'modal': dict(label='モーダル表示', cat='説明', page='both', cms=['show-modal', 'modal'],
    fields=[('title', '見出し', 'multi'), ('lead', '本文', 'multi'), ('cta', '閉じるボタン文言', 'text')],
    data={'title': 'モーダル見出し', 'lead': 'モーダル内に表示する説明文が入ります。', 'cta': '閉じる'}),
  'button': dict(label='CTA（ボタン）', cat='アクション', page='both', cms=['cta'],
    fields=[('label', 'ボタン文言', 'text'), ('href', '遷移先', 'text'), ('measure', '計測方法', 'text')],
    data={'label': '友だちを紹介する', 'href': '', 'measure': ''}),
  'invite-form': dict(label='紹介フォーム', cat='アクション', page='inviter', cms=['invite-form'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('f1', '項目1', 'text'), ('f2', '項目2', 'text'), ('f3', 'メッセージ欄の見出し', 'text'),
            ('msg', '初期メッセージ（送信文テンプレート）', 'multi'), ('cta', 'LINEボタン文言', 'text')],
    data={'title': 'クーポンを送ろう', 'f1': 'あなたのお名前', 'f2': 'あなたのメールアドレス', 'f3': 'お相手へのメッセージ',
          'msg': '紹介するとふたりとも特典がもらえるキャンペーン中だよ。よかったら使ってね。', 'cta': 'LINEで友だちに送る'}),
  'guest-form': dict(label='ゲストフォーム', cat='アクション', page='guest', cms=['guest-form'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('f1', '項目1', 'text'), ('f2', '項目2', 'text'), ('cta', '送信ボタン文言', 'text')],
    data={'title': 'クーポンを受け取る', 'f1': 'お名前', 'f2': 'メールアドレス', 'cta': 'クーポンを受け取る'}),
  'invitation-code': dict(label='クーポンコード', cat='アクション', page='guest', cms=['invitation-code', 'coupon-code'],
    fields=[('eyebrow', '見出しラベル（英字）', 'text'), ('title', '見出し', 'multi'), ('lead', '説明', 'text'), ('code', 'コード表示', 'text'), ('cta', 'コピーボタン文言', 'text')],
    data={'title': 'クーポンコード', 'code': 'XXXX-XXXX', 'cta': 'コードをコピー'}),
  'client-site-link': dict(label='クライアントサイトのリンク', cat='アクション', page='both', cms=['client-site-link'],
    fields=[('title', '見出し', 'multi'), ('cta', 'ボタン文言', 'text'), ('fine', 'ボタン下の注記', 'text'),
            ('href', '遷移先', 'text'), ('measure', '計測方法', 'text')],
    data={'title': 'サイトで予約する', 'cta': '公式サイトへ', 'href': '', 'measure': ''}),
  'coming-form-link': dict(label='来店計測へのリンク', cat='アクション', page='guest',
    cms=['coming-form-link', 'client-site-coming-form-link'],
    fields=[('title', '見出し', 'multi'), ('cta', 'ボタン文言', 'text'), ('fine', 'ボタン下の注記', 'text')],
    data={'title': '来店を報告する', 'cta': '来店報告フォームへ'}),
  'please-read': dict(label='必ずお読みください', cat='規約・フッター', page='both',
    cms=['please-read-text-editor', 'please-read-text-editor2'],
    fields=[('title', '見出し', 'text'), ('bullets', '箇条書き', 'list')],
    data={'title': '必ずお読みください', 'bullets': [
      'ご自身を紹介しての申込は無効となります。',
      '特典進呈は、紹介経由でのご利用が確認できた場合に限ります。',
      '紹介から申込までの有効期限は90日以内です。']}),
  'notice-list': dict(label='注意点などの箇条書きリスト', cat='規約・フッター', page='both', cms=['notice-list', 'attention-list'],
    fields=[('title', '見出し', 'text'), ('bullets', '箇条書き', 'list')],
    data={'title': '注意点', 'bullets': [
      '本キャンペーンの内容は予告なく変更・終了する場合があります。',
      '不正と判断された場合、特典は無効となります。',
      '特典の再発行・換金はできません。']}),
  'footer': dict(label='フッター（規約リンク）', cat='規約・フッター', page='both', cms=['footer'],
    fields=[('name', '表示名', 'text'), ('a', 'リンク1', 'text'), ('b', 'リンク2', 'text')],
    data={'name': '', 'a': '利用規約', 'b': 'プライバシーポリシー'}),
  'invitation-banner': dict(label='フローティングバナー', cat='規約・フッター', page='both',
    cms=['invitation-banner', 'guest-banner', 'floating-banner-with-timer', 'floating-banner-with-timer2'],
    fields=[('cta', 'バナー文言', 'text')], data={'cta': '今すぐクーポンをシェア'}),
}

# 全コンポーネント共通の設定（CMS のコンポーネント編集欄。スクリーンショットで確認できたもの）
COMMON_SETTINGS = [
    ('id', 'コンポーネントのID', 'ページ内リンクの飛び先に使える（CTA のリンク先に #ID を書く）'),
    ('label', 'コンポーネントのラベル', '管理用の名前'),
    ('hidden', '非表示にする', '一時的に隠す'),
    ('style.border', 'スタイル設定：枠線で囲う', 'true / false'),
    ('style.bg', 'スタイル設定：背景色', 'カラーコード。style.bgOpacity で透明度（0〜100%）'),
    ('style.padding', 'スタイル設定：余白（全体）', 'px'),
]
# リッチテキスト欄（見出し・本文・ボタン文言など）で指定できるもの
RICH_TEXT = 'H1〜H6、太字・斜体・取り消し線・下線、画像、リンク、箇条書き・番号付き、左右中央揃え、フォント、サイズ、文字色、背景色'
# ページ全体の設定（CMS のページ設定欄）
PAGE_SETTINGS = [
    ('theme', 'テーマ選択', '例：ゴシック／フォント標準。ページ全体のフォントが決まる'),
    ('title', 'ページのタイトル', '必須'),
    ('description', 'ページのdescription', '必須'),
    ('ogp', 'OGP画像', '必須。シェア時に表示される画像'),
    ('bgImage', '背景画像', 'ページの背景画像（表示のされ方は要確認）'),
    ('headScript', 'スクリプト（head）に挿入', 'ボタン色などの CSS 調整もここに入れる'),
    ('bodyScript', 'スクリプト（</body>の直前）に挿入', '任意のスクリプト'),
    ('threeStepForm', '3ステップフォームを使用する', 'ON / OFF（挙動は要確認）'),
    ('index', 'インデックスを許可する', '有効 / 無効'),
]
# 色の変え方（CMS 上の手段）。セレクタは確認できたものだけ載せる
COLOR_HOWTO = [
    ('背景色', '各コンポーネントの「スタイル設定」→ 背景色・透明度'),
    ('文字色・文字の背景色', 'リッチテキスト欄の「文字色」「背景色」'),
    ('ボタンの形', 'ヘッダーは「ボタンスタイル」で角丸／四角を選択（他コンポーネントは要確認）'),
    ('ボタンの色', 'ページ設定の「スクリプト（head）に挿入」に CSS を書く。確認済みのクラス：'
               '`.formBtn--mailto`（紹介フォームの「メールで送る」）。他のボタンのクラス名は要確認'),
    ('KV・装飾の多い見出し', '画像で作って画像コンポーネントに入れる（CMS の部品で色や装飾を作り込まない）'),
]

# CMS には存在するが、このスキルの構成では使わないと決めたもの（使う場合は担当者に相談）
EXCLUDED = {'table': '表', 'video': 'ビデオ（YouTube埋め込みで代替）', 'pdf': 'PDFファイル',
            'download-button': 'ダウンロードボタン'}

TEMPLATE = {
  'inviter': ['brand-logo', 'kv-image', 'benefits', 'flow', 'hint', 'invite-form', 'invitation-detail', 'faq',
              'please-read', 'notice-list', 'footer', 'invitation-banner'],
  'guest': ['brand-logo', 'kv-image', 'coupon-message', 'benefits', 'flow', 'guest-form', 'invitation-code', 'faq',
            'please-read', 'notice-list', 'footer', 'invitation-banner'],
}
PAGE_LABEL = {'inviter': '紹介者ページ', 'guest': 'ゲストページ'}

# invy CMS クラス（invyBlockEditor-<suffix>）→ ブロック型
CMS_TO_TYPE = {}
for _t, _b in BLOCKS.items():
    for _c in _b['cms']:
        CMS_TO_TYPE.setdefault(_c, _t)
CMS_TO_TYPE.update({'keyvisual': 'kv-image', 'video': 'youtube', 'table': 'accordion-list',
                    'pdf': 'text-editor', 'download-button': 'button'})


def defaults(t):
    return copy.deepcopy(BLOCKS[t].get('data', {}))


def image_slots(t, data):
    """ブロックの画像スロット一覧 [(slot, 表示名, w, h)]。{i} は項目数ぶん展開する。"""
    out = []
    for slot, name, w, h in BLOCKS[t].get('images', []):
        if '{i}' in slot:
            n = len(data.get('rows') or data.get('slides') or data.get('steps') or []) or data.get('count', 0)
            out += [(slot.format(i=i), f'{name}{i + 1}', w, h) for i in range(n)]
        elif slot == 'ctaImg' and data.get('ctaType') != 'image':
            continue
        else:
            out.append((slot, name, w, h))
    return out


def to_md():
    L = ['# invy CMS ブロックカタログ', '',
         '> `scripts/catalog.py` から生成（`python3 scripts/catalog.py --md > references/03-cms-blocks.md`）。',
         '> ここを直接直さず、`catalog.py` を直して再生成する。', '',
         'LP はこのカタログのブロックだけで組む。`type` は spec.json に書く値、`CMSクラス` は invy CMS の',
         '`invyBlockEditor-<クラス>`。画像サイズはツール上の既定比率（pt、×3 で px）で、**CMS 側の推奨入稿サイズは要確認**。', '',
         '| ページ | 意味 |', '|---|---|', '| both | 紹介者・ゲスト両方 |', '| inviter | 紹介者ページのみ |', '| guest | ゲストページのみ |', '']
    for cat in CATS:
        L += [f'## {cat}', '']
        for t, b in BLOCKS.items():
            if b['cat'] != cat:
                continue
            L.append(f"### {b['label']}　`{t}`")
            L.append(f"- ページ：{b['page']}　／　CMSクラス：{', '.join('`' + c + '`' for c in b['cms'])}")
            L.append('- 入力項目：' + '、'.join(f"`{k}` {n}" for k, n, _ in b['fields']))
            if b.get('images'):
                L.append('- 画像：' + '、'.join(f"`{s}` {n}（{w}×{h}pt）" for s, n, w, h in b['images']))
            L.append('')
    L += ['## 全コンポーネント共通の設定', '', '| spec のキー | CMS の項目 | メモ |', '|---|---|---|']
    L += [f'| `{k}` | {n} | {m} |' for k, n, m in COMMON_SETTINGS]
    L += ['', f'リッチテキスト欄で指定できるもの：{RICH_TEXT}', '']
    L += ['## ページ全体の設定', '', '| spec のキー（pageSettings） | CMS の項目 | メモ |', '|---|---|---|']
    L += [f'| `{k}` | {n} | {m} |' for k, n, m in PAGE_SETTINGS]
    L += ['', '## 色の変え方（CMS 上の手段）', '', '| 変えたいもの | CMS でのやり方 |', '|---|---|']
    L += [f'| {a} | {b} |' for a, b in COLOR_HOWTO]
    L += ['', 'ここに無い手段で色を当てたデザインは、CMS で再現できない前提で扱う。', '']
    L += ['## カタログ外（CMSにはあるが、このスキルでは使わない）', '']
    L += [f'- `{k}`：{v}' for k, v in EXCLUDED.items()]
    L += ['', '## 新規作成時の標準構成', '']
    for p, ts in TEMPLATE.items():
        L.append(f"- {PAGE_LABEL[p]}：" + ' → '.join(BLOCKS[t]['label'] for t in ts))
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    if '--md' in sys.argv:
        sys.stdout.write(to_md())
    else:
        print(json.dumps({t: {'label': b['label'], 'page': b['page'], 'fields': [f[0] for f in b['fields']]}
                          for t, b in BLOCKS.items()}, ensure_ascii=False, indent=1))
