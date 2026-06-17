---
name: create-poll-pages
description: poll カテゴリのページを一括作成 + タグ付与する `scripts/temp/create_poll_pages.py` の使い方ガイド。コンテスト等の決選投票で `poll:<prefix>-<variable>` 形式のページを複数まとめて作りたい時、および投票ハブに貼るリスト形式 (iframe 入り) を生成したい時に使用。使用タイミング: (1) コンテスト投票用 poll ページを作る依頼時、(2) ユーザーが「投票ページ作って」「pollページ作成」等を言及した時、(3) スクリプトの引数・設定の確認時。
---

# poll ページ作成スクリプト

`scripts/temp/create_poll_pages.py` は、Wikidot の `poll:` カテゴリ配下に複数ページをまとめて作成し、タグ付与までを行う uv script。投票ハブに貼り付けるリスト形式 (iframe 入り) も同時に出力する。

## 前提

- wikidot.py 利用 → `wikidot-py-usage` スキル参照 (search_pages 問題を回避するパターンで実装済)
- 認証: `.env` の `WIKIDOT_USERNAME` / `WIKIDOT_PASSWORD`
- テスト先サイト: **`pseudo-scp-jp` のみ** (sandbox3 等は使用禁止)

## 1. スクリプトの場所

`scripts/temp/create_poll_pages.py`

## 2. 使い方

### 2.1 設定の編集

スクリプト冒頭の `CONFIG` ブロックを書き換える:

```python
SITE = "scp-jp"                       # 対象サイト (unix_name)
PREFIX = "2026summercontest"          # poll:<PREFIX>-<variable>
PAGE_TITLE = "2026年夏コン ..."        # placeholder 利用可
EDIT_COMMENT = "..."                   # 編集コメント
TAGS = ["jp", "投票"]                 # 付与タグ
PAGE_SOURCE_TEMPLATE = """..."""     # ページソース (placeholder 利用可)
LIST_ITEM_TEMPLATE = """..."""        # 出力リスト 1 項目 (placeholder 利用可)
ITEMS = [
    {"theme": "王",     "variable": "king"},
    {"theme": "夢",     "variable": "dream"},
    ...
]
```

**テンプレート placeholder:**
- `{theme}` テーマ表記 (例: `"王"`)
- `{variable}` fullname 末尾 (例: `"king"`)
- `{prefix}` `PREFIX`
- `{site}` 対象サイト unix_name
- `{index}` 1 始まりの番号 (リスト出力のみ)
- `ITEMS[i]["extra"]` に dict を入れれば追加 placeholder を渡せる

### 2.2 実行コマンド

| コマンド | 内容 |
|---------|------|
| `uv run scripts/temp/create_poll_pages.py --dry-run` | ログインなし。作成内容とリスト出力を表示 |
| `uv run scripts/temp/create_poll_pages.py --dry-run --site pseudo-scp-jp` | テスト先で dry-run |
| `uv run scripts/temp/create_poll_pages.py --site pseudo-scp-jp` | テスト先で本番作成 |
| `uv run scripts/temp/create_poll_pages.py` | 本番 (CONFIG の SITE で実行) |
| `uv run scripts/temp/create_poll_pages.py --list-only` | 作成スキップ。リスト形式のみ出力 |
| `uv run scripts/temp/create_poll_pages.py --force` | 既存ページを上書き編集 (本番では原則使わない) |

### 2.3 出力

- **stderr (logger)**: 作成・タグセットの進捗とサマリー
- **stdout**: 投票ハブに貼り付け可能なリスト形式 (iframe 入り)

リストはユーザーにそのまま渡せるよう、最終応答ではコードブロックで提示する。

## 3. 動作の流れ (内部)

1. `site.page.create()` を呼ぶ
2. 結果に関わらず、ページ HTML を `httpx` で GET
3. `WIKIREQUEST.info.pageId` を正規表現で抽出
4. `<div class="page-tags">` を BeautifulSoup でパースして既存タグ取得
5. `existing_tags + TAGS` を merge して `saveTags` AMC を直接叩く
6. リスト形式を組み立てて stdout へ

`site.page.create` が `NotFoundException` を投げても (search_pages の false-negative)、savePage 自体は成功しているので 2 以降の処理で page_id を確実に取れる。詳細: `wikidot-py-usage` スキル。

## 4. 実行ワークフロー (推奨)

1. **CONFIG を編集**: `SITE`/`PREFIX`/`ITEMS`/`PAGE_SOURCE_TEMPLATE` 等
2. **dry-run** で内容確認: `--dry-run --site pseudo-scp-jp`
3. **pseudo-scp-jp で本番テスト**: `--site pseudo-scp-jp` → ブラウザでタグとソース確認
4. **テスト時のページは pseudo-scp-jp で残してよい** (再テスト時は同じ prefix なら `exists` パスで page_id 取得→タグ再セット)
5. **本番 (scp-jp) 実行**: `uv run scripts/temp/create_poll_pages.py`
6. **stdout のリスト形式をユーザーへコードブロックで提示**

## 5. 注意事項

- **機能追加後の最初の実行は必ず `--dry-run`**。dry-run を外した状態で実行→本番作成事故を避ける
- **テスト先は `pseudo-scp-jp` 専用**。sandbox3 等は使用禁止
- 本番作成 (`scp-jp`) はユーザー許可を得てから
- `TAGS` 変更時は既存ページの既存タグも考慮 (`saveTags` は全置換だが既存タグは保持する merge ロジックあり)
- `.env` 未設定でも dry-run は動く

## 6. 再利用 (別コンテスト等)

スクリプトは汎用化済。別用途で使う場合は `CONFIG` ブロックの以下を書き換える:

- `PREFIX`: 新しい prefix (例: `2027summercontest`)
- `PAGE_TITLE` / `EDIT_COMMENT`
- `PAGE_SOURCE_TEMPLATE` 内のコンテスト名・スレッド URL
- `ITEMS`: 新テーマ一覧 (variable は英訳 kebab-case 推奨)

## 参照

- スクリプト本体: `scripts/temp/create_poll_pages.py`
- wikidot.py 利用ガイド: `wikidot-py-usage` スキル
