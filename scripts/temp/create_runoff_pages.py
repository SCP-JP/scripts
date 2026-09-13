#!/usr/bin/env python3
"""
コンテスト決選投票用 poll ページの作成と、ハブ貼り付け用コードの出力

ページ作成・タグ付与は create_poll_pages.py の実装 (search を使わない HTML 直読み + saveTags) を流用する。
CONFIG の ITEMS に選出記事を入れて使う。

実行例:
  .venv/bin/python scripts/temp/create_runoff_pages.py --dry-run
  .venv/bin/python scripts/temp/create_runoff_pages.py --site pseudo-scp-jp
  .venv/bin/python scripts/temp/create_runoff_pages.py --code-only
"""

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import create_poll_pages as cpp  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

logger = cpp.logger

# ========================================
# CONFIG
# ========================================

HUB = "yumecontest2026-hub"
PREFIX = "yumecon26"
CONTEST_SHORT = "夢コン26"
TAGS = ["jp", "投票"]
EDIT_COMMENT = "夢のコンテスト決選投票ページの作成"
THEME_URL = "https://scp-jp.wdfiles.com/local--code/yumecontest2026-hub/1"

# 部門の表示順と、poll タイトルに使う部門タグ
DIVISIONS = [("夢想部門", "scp"), ("泡影部門", "goi-format"), ("陶酔部門", "tale")]

# 選出記事: division は DIVISIONS の表示名、rating は予選終了時点の評価 (投稿時評価として載せる)
ITEMS: list[dict] = [
    # {"division": "陶酔部門", "fullname": "mortal-emulator-dream-dream", "rating": 103},
]

PAGE_SOURCE_TEMPLATE = """\
[[>]]
[[module Rate]]
[[/>]]
[[module ThemePreviewer noUi="true"]]
[[div class="blockquote pollNote"]]
このページは**[[[{hub}|]]]**の決選投票用ページです。
* **対象記事: [[[{fullname}|]]]**
* **投稿時評価: {rating}**
[[/div]]
"""

ITEM_CODE_TEMPLATE = """\
[[module listpages category="*" fullname="{fullname}" limit="1" separate="no" wrapper="no"]]
[[div_ class="runoff-item"]]
[[div_ class="runoff-heading"]]
%%title_linked%%
[[/div]]
[[div_ class="runoff-author"]]
by [[user %%created_by_unix%%]]
[[/div]]
[[div_ class="runoff-voting"]]
評価： [[span class="runoff-voting-value"]]%%rating%%[[/span]]
[[/div]]
[[div_ class="runoff-ratemodule"]]
[[iframe http://{site}.wikidot.com/{poll_fullname}?theme_url={theme_url} scrolling="no" style="width:100%;height:1.75em;overflow:hidden;" frameborder="0"]]
[[/div]]
[[/div]]
[[/module]]
"""


def poll_fullname(item: dict, prefix: str) -> str:
    return f"poll:{prefix}-{item['fullname']}"


def build_code(items: list[dict], site: str, prefix: str) -> str:
    # 空行の入れ方は einoshima:code20260913 に合わせる (先頭部門のみ見出し直後に空行なし)
    out = ["-----", "", "", "+ 決選投票"]
    first = True
    for division, _ in DIVISIONS:
        members = [it for it in items if it["division"] == division]
        if not members:
            continue
        out.append(f"++* {division}")
        if not first:
            out.append("")
        first = False
        out.append('[[div_ class="runoff-container"]]')
        for it in members:
            out.append(ITEM_CODE_TEMPLATE.format(
                fullname=it["fullname"], site=site, poll_fullname=poll_fullname(it, prefix), theme_url=THEME_URL,
            ).rstrip("\n"))
            out.append("")
        out.append("[[/div]]")
        out.append("")
    out.append("-----")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="scp-jp")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--code-only", action="store_true")
    ap.add_argument("--prefix", default=PREFIX)
    ap.add_argument("--items", help="選出記事の JSON ファイル ([{division, fullname, rating}])。省略時は CONFIG の ITEMS")
    args = ap.parse_args()
    load_dotenv()

    items = ITEMS
    if args.items:
        with open(args.items, encoding="utf-8") as f:
            items = json.load(f)
    division_tag = dict(DIVISIONS)
    for it in items:
        if it["division"] not in division_tag:
            sys.exit(f"未知の部門: {it}")

    if not args.code_only:
        # create_poll_pages の作成処理を、この CONFIG で動かす
        cpp.TAGS = TAGS
        cpp.EDIT_COMMENT = EDIT_COMMENT
        cpp.PAGE_TITLE = "{title}"
        cpp.PAGE_SOURCE_TEMPLATE = "{source}"
        poll_items = [{
            "theme": it["fullname"],
            "variable": it["fullname"],
            "extra": {
                "title": f"{CONTEST_SHORT}決選投票-{division_tag[it['division']]}/{it['fullname']}",
                "source": PAGE_SOURCE_TEMPLATE.format(hub=HUB, fullname=it["fullname"], rating=it["rating"]),
            },
        } for it in items]
        cpp.validate_items(poll_items)
        results = cpp.create_pages(poll_items, args.site, args.prefix, args.dry_run, force=False)
        logger.info(f"results: {results}")

    print(build_code(items, args.site, args.prefix))


if __name__ == "__main__":
    main()
