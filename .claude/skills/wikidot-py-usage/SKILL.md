---
name: wikidot-py-usage
description: wikidot.py (4.x) 利用ガイド。Wikidot サイト操作 (ページ作成・編集・タグ・フォーラム等) を実装する時に使用。llms.txt の参照方法と、ListPagesModule のインデックス遅延で search_pages が落ちるケースの回避パターン (HTML直読み + AMC 直叩き) を含む。使用タイミング: (1) wikidot.py で新規実装、(2) 既存スクリプト修正、(3) ページ作成系で NotFoundException / 既存ページ取得失敗が出た時。
---

# wikidot.py 利用ガイド

このリポジトリは [wikidot.py 4.x](https://github.com/ukwhatn/wikidot.py) (`wikidot>=4.0.1,<5`) を `scripts/` 配下のスクリプトで使用する。実装前に本ガイドの方針を確認すること。

## 1. 仕様の一次ソース

公式 docstring + `llms.txt` を一次ソースとする。コード補完や記憶に頼らない。

### 1.1 llms.txt の取得

```bash
gh api repos/ukwhatn/wikidot.py/contents/llms.txt --jq '.content' | base64 -d
```

- Web 経由でも参照可: https://github.com/ukwhatn/wikidot.py/blob/main/llms.txt
- `Client` / `Site` / `Page` / `ListPagesModule` / 各 Accessor の API 一覧と signature が整理されている

### 1.2 docstring 確認 (ローカル)

`uv run` で venv にインストール済の場合:

```bash
ls /Users/ukwhatn/workspace/scp/scripts/.venv/lib/python3.12/site-packages/wikidot/module/
# page.py, site.py, forum_*.py, ...
```

不明な挙動は llms.txt → 該当モジュールの docstring → 実装の順で確認する。

## 2. 認証・基本パターン

```python
import os
from dotenv import load_dotenv
import wikidot

load_dotenv()

with wikidot.Client(
    username=os.environ["WIKIDOT_USERNAME"],
    password=os.environ["WIKIDOT_PASSWORD"],
) as client:
    site = client.site.get("scp-jp")
    # ... 操作 ...
```

- 認証は `.env` の `WIKIDOT_USERNAME` / `WIKIDOT_PASSWORD` (`.env.example` 参照)
- 既存 `scripts/temp/` 配下のスクリプトと同じパターンを踏襲

## 3. ページ作成時の注意 (重要)

### 3.1 search_pages 検証問題

`site.page.create()` および `site.page.get()` は内部で `PageCollection.search_pages` (ListPagesModule) を使う。

新規作成直後 / 既存だが listing 反映前のページに対しては **インデックス遅延** で 0 件返り、以下の false-negative が出る:

| 関数 | 投げられる例外 | 実体の状態 |
|------|---------------|-----------|
| `site.page.create()` | `NotFoundException("Page creation failed: ...")` | savePage AMC は成功・実体は作られている |
| `site.page.get(fullname, raise_when_not_found=False)` | `None` を返す | 実体は存在する |

これは **頻発する**。ページ作成系スクリプトでは search ベースの後処理に頼らない。

### 3.2 推奨パターン: HTML直読み + AMC直叩き

ページ作成 → `page_id` 取得 → タグ付与 等の一連の処理は、以下の手順で実装する。

```python
import re
import httpx
from bs4 import BeautifulSoup
from wikidot.common import exceptions as wd_exceptions

PAGE_ID_RE = re.compile(r"WIKIREQUEST\.info\.pageId\s*=\s*(\d+)\s*;")


def fetch_page_html(unix_name: str, fullname: str, ssl: bool = True) -> str | None:
    scheme = "https" if ssl else "http"
    url = f"{scheme}://{unix_name}.wikidot.com/{fullname}"
    with httpx.Client(follow_redirects=True, timeout=30) as c:
        resp = c.get(url)
    return resp.text if resp.status_code == 200 else None


def parse_page_id(html: str) -> int | None:
    m = PAGE_ID_RE.search(html)
    return int(m.group(1)) if m else None


def parse_existing_tags(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    container = soup.find("div", class_="page-tags")
    if not container:
        return []
    return [a.get_text(strip=True) for a in container.find_all("a") if a.get_text(strip=True)]


def set_tags_via_amc(site, page_id: int, tags: list[str]) -> None:
    site.amc_request([{
        "tags": " ".join(tags),
        "action": "WikiPageAction",
        "event": "saveTags",
        "pageId": page_id,
        "moduleName": "Empty",
    }])
```

### 3.3 ページ作成の制御フロー

```python
try:
    site.page.create(fullname=fn, title=t, source=s, comment=c)
    status = "created"
except wd_exceptions.TargetExistsException:
    status = "exists"
except wd_exceptions.NotFoundException:
    # 検証 search の false-negative。savePage 自体は成功
    status = "created_via_lookup"

html = fetch_page_html(site.unix_name, fn, site.ssl_supported)
page_id = parse_page_id(html)
existing_tags = parse_existing_tags(html)

# タグ付与 (既存タグを保持して merge)
new_tags = existing_tags + [t for t in TAGS if t not in existing_tags]
set_tags_via_amc(site, page_id, new_tags)
```

**注意:**
- `saveTags` は **全置換**。必ず既存タグを含めて送信
- `existing_tags` の取得は HTML の `<div class="page-tags">` から
- `page.tags` / `page.commit_tags()` は page object (= search 経由) が必要なので、本パターンでは使えない

## 4. 既存スクリプトでの実装例

| スクリプト | 関連処理 |
|-----------|---------|
| `scripts/temp/create_poll_pages.py` | 上記推奨パターンの完全実装 (作成 → page_id 取得 → タグセット) |
| `scripts/temp/remove_initial_tags.py` | search が機能する既存ページのタグ削除 (listing 反映済の前提) |
| `scripts/temp/rename_4000jp.py` | リネーム + 編集 |

新規にページ作成系スクリプトを書く場合は `create_poll_pages.py` のパターンを踏襲する。

## 5. PEP 723 ヘッダ (uv script)

ページ作成系で本ガイドの推奨パターンを使うなら、以下を `requires-python` 直下に置く:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "wikidot>=4.0.1,<5",
#     "python-dotenv>=1.0.0",
#     "httpx",
#     "beautifulsoup4",
#     "lxml",
# ]
# ///
```

## 6. dry-run 必須

ページ作成・編集・削除を行うスクリプトは `--dry-run` を必ず実装し、機能追加後の最初の実行は必ず dry-run で確認する。本番投入は dry-run の出力をユーザーが確認してから。

## 参照

- llms.txt: https://github.com/ukwhatn/wikidot.py/blob/main/llms.txt
- 詳細サンプル: `references/page-creation-pattern.md`
