# SCP-JP Scripts

SCP-JP / SCP-JP-Sandbox3 向けの自動ページ管理スクリプト群

## 処理対象

### 1. new_page/tagging.py

**タスク1: 剪定対象合作へのタグ付与**

| 項目 | 内容 |
|------|------|
| サイト | scp-jp |
| カテゴリ | `anomalous-jp`, `extranormal-events-jp`, `video-log-of-scp-1779-jp`, `poem`, `log-of-unexplained-locations-jp`, `scp-flavor` |
| 条件 | `jp` または `剪定対象-子` タグがないページ |
| 追加タグ | `jp`, `剪定対象-子` |

**タスク2: SB3ポータルページへのinitial_Xタグ付与**

| 項目 | 内容 |
|------|------|
| サイト | scp-jp-sandbox3 |
| カテゴリ | `portal` |
| 条件 | `initial_*` タグがないページ、`非使用ユーザー` タグなし |
| 追加タグ | `initial_X` (Xは作成者unix_nameの頭1文字、a-z/0-9以外は`null`、作成者不明は`非使用ユーザー`) |

### 2. collab_deletion/notice.py

**タスク: 低評価剪定対象合作への削除通知**

| 項目 | 内容 |
|------|------|
| サイト | scp-jp |
| カテゴリ | `anomalous-jp`, `extranormal-events-jp`, `video-log-of-scp-1779-jp`, `poem`, `log-of-unexplained-locations-jp`, `scp-flavor` |
| 条件 | rating <= -3 かつ `合作記事剪定通知` タグなし |
| 追加タグ | `合作記事剪定通知` |

### 3. collab_deletion/exec.py

**タスク: 剪定通知済みページの処理**

| 項目 | 内容 |
|------|------|
| サイト | scp-jp |
| 対象 | `合作記事剪定通知` タグ付きページ |
| rating <= -3 | タグ全削除 → `deleted:<category>:<name>-<random6>` にリネーム |
| rating >= -2 | `合作記事剪定通知` タグのみ削除（回復） |

## GitHub Actions

スクリプトはGitHub Actionsで自動実行されます。

| ワークフロー | スケジュール |
|-------------|-------------|
| tagging.yml | 毎日 04:00 JST |
| collab-notice.yml | 毎月1日 09:00 JST |
| collab-exec.yml | 毎月4日 09:00 JST |

### 必要なSecrets

リポジトリのSettings → Secrets and variables → Actionsで設定:

- `WIKIDOT_USERNAME`
- `WIKIDOT_PASSWORD`
- `DISCORD_WEBHOOK_URL`

## ローカル実行

### セットアップ

```bash
# uvのインストール
curl -LsSf https://astral.sh/uv/install.sh | sh

# 環境変数の設定
cp .env.example .env
# .envを編集
```

### 実行

```bash
# Dry-run（変更せずに対象を確認）
make dry-tag      # タグ付与
make dry-notice   # 剪定通知
make dry-delete   # 剪定実行

# 本番実行
make run-tag
make run-notice
make run-delete
```

## 通知

各スクリプト実行完了時にDiscord webhookで結果を通知します。

| 色 | 意味 |
|----|------|
| 緑 | 正常終了 |
| 黄 | 削除処理あり |
| 赤 | エラー発生 |

## 技術仕様

- Python 3.11+
- [wikidot.py](https://github.com/ukwhatn/wikidot.py) v4.x
- PEP 723 形式の uv script（単一ファイル実行）
- GitHub Actions による定期実行

## ライセンス

MIT
