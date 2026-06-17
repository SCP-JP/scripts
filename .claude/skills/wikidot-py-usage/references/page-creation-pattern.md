# ページ作成: search_pages 問題と回避パターン

## 問題の詳細

wikidot.py 4.x の `Page.create_or_edit()` は末尾で次の検証を行う:

```python
res = PageCollection.search_pages(site, SearchPagesQuery(fullname=fullname))
if len(res) == 0:
    raise exceptions.NotFoundException(f"Page creation failed: {fullname}")
return res[0]
```

`search_pages` は内部で **ListPagesModule** を AMC 経由で叩く。これは ListPages のインデックスに依存するため、`savePage` イベント自体が成功しても新規ページがすぐに listing に反映されない場合がある。結果、以下が起きる:

- `site.page.create()` が `NotFoundException` を投げる (実体は作られている)
- `site.page.get(fullname)` が `None` を返す (実体は存在する)
- 直後の `page.commit_tags()` 等が呼べない (page object が取れない)

## 影響範囲

| 操作 | 影響 |
|------|------|
| `site.page.create` | 作成成功でも `NotFoundException` 例外 |
| `site.page.get` | listing 未反映なら `None` / `NotFoundException` |
| `site.pages.search` | 同上 |
| `page.commit_tags` | page object 取得失敗で呼べない |
| `page.edit` | 既存ページの page_id 取得失敗で呼べない |

## 回避パターン (全体像)

「**savePage は信用する。後段は HTML 直読み + AMC 直叩きで補う**」が原則。

### Step 1: 作成試行 (例外は分類して握る)

```python
from wikidot.common import exceptions as wd_exceptions

try:
    site.page.create(fullname=fn, title=t, source=s, comment=c)
    status = "created"
except wd_exceptions.TargetExistsException:
    # 既存ページ。AMC 経由の存在チェックなので確実
    status = "exists"
except wd_exceptions.NotFoundException:
    # search 検証の false-negative。savePage は成功している
    status = "created_via_lookup"
```

### Step 2: ページ HTML を直接 GET

```python
import httpx

def fetch_page_html(unix_name: str, fullname: str, ssl: bool = True) -> str | None:
    scheme = "https" if ssl else "http"
    url = f"{scheme}://{unix_name}.wikidot.com/{fullname}"
    for _ in range(5):
        try:
            with httpx.Client(follow_redirects=True, timeout=30) as c:
                resp = c.get(url)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        time.sleep(2)
    return None
```

### Step 3: page_id と既存タグを抽出

```python
import re
from bs4 import BeautifulSoup

PAGE_ID_RE = re.compile(r"WIKIREQUEST\.info\.pageId\s*=\s*(\d+)\s*;")

def parse_page_id(html: str) -> int | None:
    m = PAGE_ID_RE.search(html)
    return int(m.group(1)) if m else None

def parse_existing_tags(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    container = soup.find("div", class_="page-tags")
    if not container:
        return []
    return [a.get_text(strip=True) for a in container.find_all("a")]
```

ページ HTML の主要ポイント:

- `<script>` 内 `WIKIREQUEST.info.pageId = <数字>;` … page_id
- `<div class="page-tags"><span><a>jp</a><a>投票</a></span></div>` … タグ一覧

### Step 4: saveTags AMC を直接叩く

```python
def set_tags_via_amc(site, page_id: int, tags: list[str]) -> None:
    site.amc_request([{
        "tags": " ".join(tags),
        "action": "WikiPageAction",
        "event": "saveTags",
        "pageId": page_id,
        "moduleName": "Empty",
    }])
```

**注意:**
- `saveTags` は **全置換**。既存タグを保持したい場合は merge してから送信
- `pageId` は `page_id` ではなくキャメルケース ("pageId")

### Step 5: 既存タグとの merge

```python
new_tags = existing_tags + [t for t in TAGS if t not in existing_tags]
set_tags_via_amc(site, page_id, new_tags)
```

## 他の AMC 直叩きパターン

ページ編集も同様に直接叩ける:

```python
# 編集ロック取得
lock_req = {
    "mode": "page",
    "wiki_page": fullname,
    "moduleName": "edit/PageEditModule",
    "force_lock": "yes",
}
lock_resp = site.amc_request([lock_req])[0].json()
lock_id = lock_resp["lock_id"]
lock_secret = lock_resp["lock_secret"]
page_revision_id = lock_resp.get("page_revision_id")

# 保存
edit_req = {
    "action": "WikiPageAction",
    "event": "savePage",
    "moduleName": "Empty",
    "mode": "page",
    "lock_id": lock_id,
    "lock_secret": lock_secret,
    "revision_id": page_revision_id or "",
    "wiki_page": fullname,
    "page_id": page_id,
    "title": new_title,
    "source": new_source,
    "comments": comment,
}
site.amc_request([edit_req])
```

ただし、編集は `page.edit()` 経由でも (page object が取れていれば) 動く。**ページ作成直後は page object が取れない**ことが本ガイドの主題なので、その場合のみ AMC 直叩きを使う。

## 実装サンプル

`scripts/temp/create_poll_pages.py` がこのパターンの完全実装。
