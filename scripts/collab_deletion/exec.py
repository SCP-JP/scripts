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
剪定通知済みページの処理
- rating <= -3: タグ全削除 + deleted:カテゴリにリネーム
- rating >= -2: 剪定通知タグのみ削除（回復扱い）
"""

import argparse
import logging
import os
import random
import string
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

NOTICE_TAG = "合作記事剪定通知"
FORUM_THREAD_ID = 12464623

COLOR_SUCCESS = 0x00FF00
COLOR_WARNING = 0xFFFF00
COLOR_ERROR = 0xFF0000


def generate_random_suffix(length: int = 6) -> str:
    """ランダムな英数字文字列を生成"""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


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


def find_notice_post(thread, year_month: str) -> int | None:
    """当月の通知ポストを探す"""
    pattern = f"剪定対象合作の削除通知のお知らせ({year_month})"

    for post in thread.posts:
        if post.title and pattern in post.title:
            return post.id
    return None


def post_forum_delete_notice(
    site: wikidot.module.site.Site,
    dry_run: bool = False,
) -> dict:
    """フォーラムに削除実施通知を投稿"""
    now = datetime.now()
    year_month = now.strftime("%Y/%m")

    title = f"剪定対象合作の削除・削除通知解除のお知らせ({year_month})"
    source = "上記剪定対象合作記事に関して、評価が回復していない記事を削除しました"

    if dry_run:
        logger.info("フォーラム投稿:")
        logger.info(f"  スレッドID: {FORUM_THREAD_ID}")
        logger.info(f"  件名: {title}")
        logger.info(f"  内容: {source}")
        logger.info("  ※当月の通知ポストがあれば返信として投稿")
        return {"posted": True, "title": title, "dry_run": True}

    try:
        thread = site.get_thread(FORUM_THREAD_ID)
        parent_post_id = find_notice_post(thread, year_month)

        if parent_post_id:
            thread.reply(source=source, title=title, parent_post_id=parent_post_id)
            logger.info(f"フォーラム投稿完了（返信先: #{parent_post_id}）: {title}")
            return {"posted": True, "title": title, "replied_to": parent_post_id}
        else:
            thread.reply(source=source, title=title)
            logger.info(f"フォーラム投稿完了（新規投稿）: {title}")
            return {"posted": True, "title": title, "replied_to": None}

    except Exception as e:
        logger.exception(f"Error posting forum notice: {e}")
        return {"posted": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="剪定実行スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="実際の変更を行わずに対象を表示")
    args = parser.parse_args()

    load_dotenv()
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    results = {
        "deleted": [],
        "recovered": [],
        "errors": [],
        "forum": None,
    }

    if args.dry_run:
        logger.info("=== DRY-RUN MODE ===")

    with wikidot.Client(
        username=os.environ["WIKIDOT_USERNAME"],
        password=os.environ["WIKIDOT_PASSWORD"],
    ) as client:
        site = client.site.get("scp-jp")
        pages = site.pages.search(tags=[NOTICE_TAG])

        for page in pages:
            try:
                if page.rating <= -3:
                    # 削除処理: タグ全削除 + リネーム
                    original_fullname = page.fullname
                    random_suffix = generate_random_suffix()

                    if ":" in original_fullname:
                        category, name = original_fullname.split(":", 1)
                        new_name = f"deleted:{category}:{name}-{random_suffix}"
                    else:
                        new_name = f"deleted:{original_fullname}-{random_suffix}"

                    if args.dry_run:
                        logger.info(f"[DRY-RUN] DELETE: {original_fullname} -> {new_name} (rating: {page.rating})")
                    else:
                        for tag in list(page.tags):
                            page.tags.remove(tag)
                        page.commit_tags()
                        page.rename(new_name)
                        logger.info(f"DELETE: {original_fullname} -> {new_name} (rating: {page.rating})")

                    results["deleted"].append(
                        {
                            "original": original_fullname,
                            "new": new_name,
                            "rating": page.rating,
                        }
                    )

                else:
                    # 回復処理: 通知タグのみ削除
                    if args.dry_run:
                        logger.info(f"[DRY-RUN] RECOVER: {page.fullname} (rating: {page.rating}): -[{NOTICE_TAG}]")
                    else:
                        page.tags.remove(NOTICE_TAG)
                        page.commit_tags()
                        logger.info(f"RECOVER: {page.fullname} (rating: {page.rating}): -[{NOTICE_TAG}]")

                    results["recovered"].append(
                        {"page": page.fullname, "rating": page.rating}
                    )

            except Exception as e:
                logger.exception(f"Error processing page {page.fullname}: {e}")
                results["errors"].append({"page": page.fullname, "error": str(e)})

        # フォーラム投稿（削除または回復処理があった場合）
        if results["deleted"] or results["recovered"]:
            results["forum"] = post_forum_delete_notice(site, dry_run=args.dry_run)

    # Discord通知（dry-run時は送信しない）
    if args.dry_run:
        logger.info("=== SUMMARY ===")
        logger.info(f"削除対象: {len(results['deleted'])}件")
        logger.info(f"回復対象: {len(results['recovered'])}件")
        logger.info(f"エラー: {len(results['errors'])}件")
        if results["forum"]:
            logger.info(f"フォーラム投稿: {'予定' if results['forum'].get('posted') else 'なし'}")
        return

    deleted_list = "\n".join(
        [
            f"- {d['original']} -> {d['new']} (rating: {d['rating']})"
            for d in results["deleted"][:5]
        ]
    )
    if len(results["deleted"]) > 5:
        deleted_list += f"\n...他 {len(results['deleted']) - 5}件"

    recovered_list = "\n".join(
        [f"- {r['page']} (rating: {r['rating']})" for r in results["recovered"][:5]]
    )
    if len(results["recovered"]) > 5:
        recovered_list += f"\n...他 {len(results['recovered']) - 5}件"

    fields = [
        {
            "name": "削除処理 (rating <= -3)",
            "value": f"{len(results['deleted'])}件\n{deleted_list}"
            if results["deleted"]
            else "0件",
            "inline": False,
        },
        {
            "name": "回復 (rating >= -2)",
            "value": f"{len(results['recovered'])}件\n{recovered_list}"
            if results["recovered"]
            else "0件",
            "inline": False,
        },
        {
            "name": "エラー",
            "value": f"{len(results['errors'])}件",
            "inline": False,
        },
    ]

    if results["forum"]:
        if results["forum"].get("posted"):
            replied_to = results["forum"].get("replied_to")
            forum_status = f"投稿済み" + (f" (返信先: #{replied_to})" if replied_to else " (新規投稿)")
        else:
            forum_status = f"失敗: {results['forum'].get('error', '不明')}"
        fields.append(
            {
                "name": "フォーラム通知",
                "value": forum_status,
                "inline": False,
            }
        )

    if results["errors"] or (results["forum"] and not results["forum"].get("posted")):
        color = COLOR_ERROR
    elif results["deleted"]:
        color = COLOR_WARNING
    else:
        color = COLOR_SUCCESS

    send_discord_notification(
        webhook_url=webhook_url,
        title="collab_deletion/exec 完了",
        description=f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        fields=fields,
        color=color,
    )


if __name__ == "__main__":
    main()
