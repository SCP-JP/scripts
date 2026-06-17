#!/usr/bin/env python3
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
"""
poll カテゴリのページを一括作成するスクリプト

用途別に冒頭の CONFIG ブロックを書き換えて使う。

機能:
  1. ``ITEMS`` に列挙したテーマごとに ``poll:<PREFIX>-<variable>`` を作成
  2. 投票ハブに貼れるリスト形式 (iframe 入り) を stdout に出力

テンプレート内で使える placeholder:
  - ``{theme}``    テーマ表記 (例: "王")
  - ``{variable}`` fullname 末尾 (例: "king")
  - ``{prefix}``   PREFIX
  - ``{site}``     対象サイトの unix_name (例: "scp-jp")
  - ``{index}``    1 始まりの番号 (リスト出力でのみ使用)

実行例:
  uv run scripts/temp/create_poll_pages.py --dry-run
  uv run scripts/temp/create_poll_pages.py
  uv run scripts/temp/create_poll_pages.py --list-only
  uv run scripts/temp/create_poll_pages.py --site scp-jp-sandbox3
"""

import argparse
import logging
import os
import re
import sys
import time

import httpx
import wikidot
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from wikidot.common import exceptions as wd_exceptions

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ========================================
# CONFIG: 用途ごとにここを編集
# ========================================

# 対象サイト (unix_name)
SITE = "scp-jp"

# poll fullname の prefix。fullname は ``poll:<PREFIX>-<variable>``
PREFIX = "2026summercontest"

# ページタイトル (空文字なら設定しない)。placeholder 利用可
PAGE_TITLE = "2026年夏コン テーマ選定決選投票: {theme}"

# 編集コメント
EDIT_COMMENT = "2026年夏コン テーマ選定決選投票ページの作成"

# 付与するタグ
TAGS: list[str] = ["jp", "投票"]

# ページソーステンプレート
PAGE_SOURCE_TEMPLATE = """\
[[>]]
[[module Rate]]
[[/>]]
[[module ThemePreviewer noUi="true"]]
[[div class="blockquote pollNote"]]
このページは**[*http://scp-jp.wikidot.com/forum/t-17950572/13 テーマ募集「13周年夏のコンテスト」]**のテーマ選定投票用ページです。
* **対象テーマ: {theme}**
[[/div]]
"""

# リスト出力 (投票ハブ貼り付け用) の 1 項目テンプレート
LIST_ITEM_TEMPLATE = """\
[[div style="border:solid 1px #999999; padding:5px; margin-bottom: 10px;"]]
[[size 200%]]候補{index}. ##24789c|{theme}##[[/size]]

**獲得票数:**

[[>]]

[[iframe http://{site}.wikidot.com/poll:{prefix}-{variable}?theme_url=http://05command-ja.wikidot.com/local--code_/how-to-poll/2 scrolling="no"  style="width:180px; height:26px;overflow:hidden;"frameborder="0"]]

[[/>]]

[[/div]]
"""

# 作成するテーマ一覧
#   theme:    ページソース・リスト中に出る日本語表記
#   variable: fullname 末尾 (英訳・kebab-case 推奨)
#   extra:    (任意) 追加 placeholder を渡したい場合はここに dict で入れる
ITEMS: list[dict] = [
    {"theme": "王",     "variable": "king"},
    {"theme": "夢",     "variable": "dream"},
    {"theme": "裏切り", "variable": "betrayal"},
    {"theme": "星",     "variable": "star"},
    {"theme": "欲",     "variable": "desire"},
]


# ========================================
# 実装
# ========================================

def build_context(item: dict, index: int, site: str, prefix: str) -> dict:
    ctx = {
        "theme": item["theme"],
        "variable": item["variable"],
        "prefix": prefix,
        "site": site,
        "index": index,
    }
    ctx.update(item.get("extra", {}))
    return ctx


def render(template: str, ctx: dict) -> str:
    try:
        return template.format(**ctx)
    except KeyError as e:
        raise KeyError(
            f"テンプレート内の placeholder {e} に対応する値がありません。"
            f" 利用可能なキー: {sorted(ctx.keys())}"
        ) from e


def validate_items(items: list[dict]) -> None:
    if not items:
        raise ValueError("ITEMS が空です")
    seen = set()
    for i, item in enumerate(items):
        if "theme" not in item or "variable" not in item:
            raise ValueError(f"ITEMS[{i}] に theme/variable がありません: {item}")
        v = item["variable"]
        if v in seen:
            raise ValueError(f"variable が重複しています: {v}")
        seen.add(v)


def build_list_output(items: list[dict], site: str, prefix: str) -> str:
    parts = []
    for i, item in enumerate(items, start=1):
        ctx = build_context(item, i, site, prefix)
        parts.append(render(LIST_ITEM_TEMPLATE, ctx))
    return "\n".join(parts)


# wikidot.py 4.x の Page.create_or_edit() / site.page.get() は内部で
# ListPagesModule (search_pages) を使うが、新規作成直後はインデックス遅延で
# 0 件が返り NotFoundException になる。一方 AMC の savePage 自体は成功している。
# そのため、ページHTMLを直接GETして page_id と既存タグを抽出し、
# saveTags AMC を直接叩くことでタグ付与を確実に行う。
PAGE_FETCH_RETRIES = 5
PAGE_FETCH_INTERVAL_SEC = 2

PAGE_ID_RE = re.compile(r"WIKIREQUEST\.info\.pageId\s*=\s*(\d+)\s*;")


def fetch_page_html(unix_name: str, fullname: str, ssl_supported: bool) -> str | None:
    scheme = "https" if ssl_supported else "http"
    url = f"{scheme}://{unix_name}.wikidot.com/{fullname}"
    last_exc = None
    for attempt in range(1, PAGE_FETCH_RETRIES + 1):
        try:
            with httpx.Client(follow_redirects=True, timeout=30) as c:
                resp = c.get(url)
            if resp.status_code == 200:
                return resp.text
            last_exc = RuntimeError(f"HTTP {resp.status_code}")
        except Exception as e:
            last_exc = e
        if attempt < PAGE_FETCH_RETRIES:
            time.sleep(PAGE_FETCH_INTERVAL_SEC)
    if last_exc:
        logger.warning(f"ページHTML取得失敗 ({unix_name}/{fullname}): {last_exc}")
    return None


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
    site.amc_request([
        {
            "tags": " ".join(tags),
            "action": "WikiPageAction",
            "event": "saveTags",
            "pageId": page_id,
            "moduleName": "Empty",
        }
    ])


def create_pages(items: list[dict], site_name: str, prefix: str, dry_run: bool, force: bool) -> dict:
    results = {"created": [], "skipped_exists": [], "errors": [], "tagged": [], "tag_failed": []}

    if dry_run:
        # dry-run はログインなしで内容のみ表示
        for i, item in enumerate(items, start=1):
            ctx = build_context(item, i, site_name, prefix)
            fullname = f"poll:{prefix}-{item['variable']}"
            title = render(PAGE_TITLE, ctx) if PAGE_TITLE else ""
            source = render(PAGE_SOURCE_TEMPLATE, ctx)
            logger.info("-" * 60)
            logger.info(f"[DRY-RUN] fullname: {fullname}")
            if title:
                logger.info(f"[DRY-RUN] title:    {title}")
            if TAGS:
                logger.info(f"[DRY-RUN] tags:     {TAGS}")
            logger.info("[DRY-RUN] source:")
            for line in source.splitlines():
                logger.info(f"  | {line}")
            results["created"].append(fullname)
        return results

    with wikidot.Client(
        username=os.environ["WIKIDOT_USERNAME"],
        password=os.environ["WIKIDOT_PASSWORD"],
    ) as client:
        site = client.site.get(site_name)

        for i, item in enumerate(items, start=1):
            ctx = build_context(item, i, site_name, prefix)
            fullname = f"poll:{prefix}-{item['variable']}"
            title = render(PAGE_TITLE, ctx) if PAGE_TITLE else ""
            source = render(PAGE_SOURCE_TEMPLATE, ctx)

            try:
                # 1. 作成試行
                status = None  # "created" | "exists" | "created_via_lookup"
                try:
                    site.page.create(
                        fullname=fullname,
                        title=title,
                        source=source,
                        comment=EDIT_COMMENT,
                    )
                    status = "created"
                    logger.info(f"作成: {fullname}")
                except wd_exceptions.TargetExistsException:
                    status = "exists"
                    logger.warning(f"既存ページ: {fullname}")
                except wd_exceptions.NotFoundException:
                    # wikidot.py 内部の検証 search が listing 遅延で 0 件 → false negative
                    # 実体は作成済み(savePage AMC は成功)
                    status = "created_via_lookup"
                    logger.info(f"作成 (検証 search は listing 未反映): {fullname}")

                # 2. ページHTMLを直接取得 → page_id と既存タグを抽出
                html = fetch_page_html(site_name, fullname, site.ssl_supported)
                if html is None:
                    raise RuntimeError(f"ページHTML取得失敗: {fullname}")

                page_id = parse_page_id(html)
                if page_id is None:
                    raise RuntimeError(f"page_id 抽出失敗: {fullname}")
                existing_tags = parse_existing_tags(html)
                logger.info(f"page_id={page_id} existing_tags={existing_tags}: {fullname}")

                if status == "exists" and not force:
                    results["skipped_exists"].append(fullname)
                else:
                    results["created"].append(fullname)

                # 3. タグセット (既存タグ保持 + 追加)
                if TAGS:
                    added = [t for t in TAGS if t not in existing_tags]
                    if added:
                        new_tags = existing_tags + added
                        try:
                            set_tags_via_amc(site, page_id, new_tags)
                            logger.info(f"タグセット {fullname}: +{added} (合計 {new_tags})")
                            results["tagged"].append(fullname)
                        except Exception as e:
                            logger.exception(f"タグセット失敗 {fullname}: {e}")
                            results["tag_failed"].append({"page": fullname, "error": str(e)})
                    else:
                        logger.info(f"タグ付与スキップ (既に付与済): {fullname}")

            except Exception as e:
                logger.exception(f"エラー: {fullname}: {e}")
                results["errors"].append({"page": fullname, "error": str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(description="poll カテゴリページの一括作成")
    parser.add_argument("--dry-run", action="store_true", help="作成せず内容のみ表示")
    parser.add_argument("--list-only", action="store_true", help="ページ作成せずリスト形式のみ出力")
    parser.add_argument("--force", action="store_true", help="既存ページを上書き編集")
    parser.add_argument("--site", type=str, default=SITE, help=f"対象サイト (デフォルト: {SITE})")
    parser.add_argument("--prefix", type=str, default=PREFIX, help=f"fullname prefix (デフォルト: {PREFIX})")
    args = parser.parse_args()

    load_dotenv()

    try:
        validate_items(ITEMS)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"site={args.site} prefix={args.prefix} items={len(ITEMS)}")

    if args.list_only:
        logger.info("リスト形式のみ出力します (--list-only)")
    else:
        if args.dry_run:
            logger.info("=== DRY-RUN MODE ===")
        results = create_pages(ITEMS, args.site, args.prefix, args.dry_run, args.force)

        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        logger.info(f"作成: {len(results['created'])}件")
        logger.info(f"既存スキップ: {len(results['skipped_exists'])}件")
        logger.info(f"タグセット成功: {len(results.get('tagged', []))}件")
        logger.info(f"タグセット失敗: {len(results.get('tag_failed', []))}件")
        logger.info(f"エラー: {len(results['errors'])}件")
        if results["errors"]:
            for err in results["errors"]:
                logger.info(f"  {err['page']}: {err['error']}")
        if results.get("tag_failed"):
            for err in results["tag_failed"]:
                logger.info(f"  tag_failed {err['page']}: {err['error']}")

    # リスト出力 (stdout)
    logger.info("=" * 60)
    logger.info("リスト形式 (stdout):")
    logger.info("=" * 60)
    print(build_list_output(ITEMS, args.site, args.prefix))


if __name__ == "__main__":
    main()
