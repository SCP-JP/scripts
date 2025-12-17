#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "wikidot>=4.0.1,<5",
#     "python-dotenv>=1.0.0",
#     "requests>=2.31.0",
# ]
# ///
"""
タスク1: 剪定対象合作カテゴリへのjp/剪定対象-子タグ付与
タスク2: SB3ポータルページへのinitial_Xタグ付与
"""

import argparse
import logging
import os
import requests
from datetime import datetime, UTC
from dotenv import load_dotenv
import wikidot

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

COLLAB_CATEGORIES = [
    "anomalous-jp",
    "extranormal-events-jp",
    "video-log-of-scp-1779-jp",
    "poem",
    "log-of-unexplained-locations-jp",
    "scp-flavor",
]

COLOR_SUCCESS = 0x00FF00
COLOR_WARNING = 0xFFFF00
COLOR_ERROR = 0xFF0000


def send_discord_notification(
    webhook_url: str,
    title: str,
    description: str,
    fields: list[dict] | None = None,
    color: int = COLOR_SUCCESS,
) -> bool:
    """Discord webhookにembed形式で通知を送信"""
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(UTC).isoformat(),
        "footer": {"text": "SCP-JP Scripts"},
    }
    if fields:
        embed["fields"] = fields

    try:
        response = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
        return 200 <= response.status_code < 300
    except requests.RequestException as e:
        logger.exception(f"Error sending Discord notification: {e}")
        return False


def get_initial_tag(unix_name: str) -> str:
    """unix_nameの頭文字からinitial_Xタグを生成"""
    if not unix_name:
        return "initial_null"
    first_char = unix_name[0].lower()
    if first_char.isalnum():
        return f"initial_{first_char}"
    return "initial_null"


def should_skip_page(page, processed_pages: set) -> bool:
    """ページをスキップすべきか判定"""
    return page.fullname in processed_pages or page.name.startswith("_")


def add_tags_to_page(page, tags: list[str], dry_run: bool) -> None:
    """ページにタグを追加"""
    if dry_run:
        logger.info(f"[DRY-RUN] {page.fullname}: +{tags}")
    else:
        for tag in tags:
            page.tags.append(tag)
        page.commit_tags()
        logger.info(f"{page.fullname}: +{tags}")


def task1_collab_tagging(client: wikidot.Client, dry_run: bool = False) -> dict:
    """剪定対象合作へのタグ付与"""
    site = client.site.get("scp-jp")
    results = {"processed": [], "errors": []}
    processed_pages = set()

    for category in COLLAB_CATEGORIES:
        # jpタグがないページを検索して両タグを付与
        pages_without_jp = site.pages.search(category=category, tags=["-jp"])
        for page in pages_without_jp:
            if should_skip_page(page, processed_pages):
                continue
            processed_pages.add(page.fullname)

            try:
                tags_to_add = ["jp"]
                if "剪定対象-子" not in page.tags:
                    tags_to_add.append("剪定対象-子")
                add_tags_to_page(page, tags_to_add, dry_run)
                results["processed"].append(page.fullname)
            except Exception as e:
                logger.exception(f"Error processing page {page.fullname}: {e}")
                results["errors"].append({"page": page.fullname, "error": str(e)})

        # 剪定対象-子タグがないページを検索（jpタグはあるがこちらがない場合）
        pages_without_sentei = site.pages.search(category=category, tags=["-剪定対象-子"])
        for page in pages_without_sentei:
            if should_skip_page(page, processed_pages):
                continue
            processed_pages.add(page.fullname)

            try:
                add_tags_to_page(page, ["剪定対象-子"], dry_run)
                results["processed"].append(page.fullname)
            except Exception as e:
                logger.exception(f"Error processing page {page.fullname}: {e}")
                results["errors"].append({"page": page.fullname, "error": str(e)})

    return results


def task2_sb3_portal_tagging(client: wikidot.Client, dry_run: bool = False) -> dict:
    """SB3ポータルページへのinitial_Xタグ付与"""
    site = client.site.get("scp-jp-sandbox3")
    results = {"processed": [], "errors": []}

    # initial_*タグを全て除外、非使用ユーザーも除外して検索
    exclude_tags = [f"-initial_{c}" for c in "abcdefghijklmnopqrstuvwxyz0123456789"] + ["-initial_null", "-非使用ユーザー"]
    pages = site.pages.search(category="portal", tags=exclude_tags)

    for page in pages:
        try:
            if page.name.startswith("_"):
                continue

            if page.created_by:
                initial_tag = get_initial_tag(page.created_by.unix_name)
            else:
                initial_tag = "非使用ユーザー"

            add_tags_to_page(page, [initial_tag], dry_run)
            results["processed"].append(page.fullname)
        except Exception as e:
            logger.exception(f"Error processing page {page.fullname}: {e}")
            results["errors"].append({"page": page.fullname, "error": str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(description="タグ付与スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="実際の変更を行わずに対象を表示")
    args = parser.parse_args()

    load_dotenv()
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]

    if args.dry_run:
        logger.info("=== DRY-RUN MODE ===")

    with wikidot.Client(
        username=os.environ["WIKIDOT_USERNAME"],
        password=os.environ["WIKIDOT_PASSWORD"],
    ) as client:
        task1_results = task1_collab_tagging(client, dry_run=args.dry_run)
        task2_results = task2_sb3_portal_tagging(client, dry_run=args.dry_run)

    # Discord通知（dry-run時は送信しない）
    if args.dry_run:
        logger.info("=== SUMMARY ===")
        logger.info(f"タスク1: 処理対象 {len(task1_results['processed'])}件, エラー {len(task1_results['errors'])}件")
        logger.info(f"タスク2: 処理対象 {len(task2_results['processed'])}件, エラー {len(task2_results['errors'])}件")
        return

    fields = [
        {
            "name": "タスク1: 剪定対象合作タグ付与",
            "value": f"処理: {len(task1_results['processed'])}件\nエラー: {len(task1_results['errors'])}件",
            "inline": True,
        },
        {
            "name": "タスク2: SB3 initial_Xタグ付与",
            "value": f"処理: {len(task2_results['processed'])}件\nエラー: {len(task2_results['errors'])}件",
            "inline": True,
        },
    ]

    total_errors = len(task1_results["errors"]) + len(task2_results["errors"])
    total_processed = len(task1_results["processed"]) + len(task2_results["processed"])

    if total_errors > 0:
        color = COLOR_ERROR
    else:
        color = COLOR_SUCCESS

    if total_processed > 0 or total_errors > 0:
        send_discord_notification(
            webhook_url=webhook_url,
            title="tool/tagging 完了",
            description=f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            fields=fields,
            color=color,
        )


if __name__ == "__main__":
    main()
