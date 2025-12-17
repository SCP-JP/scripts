#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "wikidot>=4.0.1,<5",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
一時スクリプト: 非使用ユーザータグがついているポータルページからinitial_*タグを削除
"""

import argparse
import logging
import os
from dotenv import load_dotenv
import wikidot

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

INACTIVE_USER_TAG = "非使用ユーザー"
INITIAL_TAGS = [f"initial_{c}" for c in "abcdefghijklmnopqrstuvwxyz0123456789"] + ["initial_null"]


def main():
    parser = argparse.ArgumentParser(description="非使用ユーザーのポータルからinitial_*タグを削除")
    parser.add_argument("--dry-run", action="store_true", help="実際の変更を行わずに対象を表示")
    args = parser.parse_args()

    load_dotenv()

    if args.dry_run:
        logger.info("=== DRY-RUN MODE ===")

    results = {"processed": [], "skipped": 0, "errors": []}

    with wikidot.Client(
        username=os.environ["WIKIDOT_USERNAME"],
        password=os.environ["WIKIDOT_PASSWORD"],
    ) as client:
        site = client.site.get("scp-jp-sandbox3")
        pages = site.pages.search(category="portal", tags=[INACTIVE_USER_TAG])

        for page in pages:
            initial_tags_on_page = [t for t in page.tags if t in INITIAL_TAGS]

            if not initial_tags_on_page:
                results["skipped"] += 1
                continue

            try:
                if args.dry_run:
                    logger.info(f"[DRY-RUN] {page.fullname}: -{initial_tags_on_page}")
                else:
                    for tag in initial_tags_on_page:
                        page.tags.remove(tag)
                    page.commit_tags()
                    logger.info(f"{page.fullname}: -{initial_tags_on_page}")

                results["processed"].append({
                    "page": page.fullname,
                    "removed_tags": initial_tags_on_page,
                })
            except Exception as e:
                logger.error(f"Error processing page {page.fullname}: {e}")
                results["errors"].append({"page": page.fullname, "error": str(e)})

    logger.info("=== SUMMARY ===")
    logger.info(f"処理: {len(results['processed'])}件")
    logger.info(f"スキップ（initial_*タグなし）: {results['skipped']}件")
    logger.info(f"エラー: {len(results['errors'])}件")


if __name__ == "__main__":
    main()
