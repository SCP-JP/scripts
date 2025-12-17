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
低評価剪定対象合作ページへの剪定通知タグ付与
条件: rating <= -3
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

NOTICE_TAG = "合作記事剪定通知"
FORUM_THREAD_ID = 12464623

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
        logger.error(f"Error sending Discord notification: {e}")
        return False


def post_forum_notice(site: wikidot.module.site.Site, dry_run: bool = False) -> dict:
    """フォーラムに剪定通知を投稿"""
    now = datetime.now()
    year_month = now.strftime("%Y/%m")

    title = f"剪定対象合作の削除通知のお知らせ({year_month})"
    source = f"""月度が変わったため合作記事のガイドラインに則り合作参加記事の剪定を行います。今月の剪定対象については下記のurlを参照してください。

[[[http://scp-jp.wikidot.com/log-of-anomalous-items-jp/tags/+%E5%90%88%E4%BD%9C%E8%A8%98%E4%BA%8B%E5%89%AA%E5%AE%9A%E9%80%9A%E7%9F%A5|Anomalousアイテム一覧-JP剪定対象]]]
[[[http://scp-jp.wikidot.com/log-of-extranormal-events-jp/tags/+%E5%90%88%E4%BD%9C%E8%A8%98%E4%BA%8B%E5%89%AA%E5%AE%9A%E9%80%9A%E7%9F%A5|超常現象記録-JP剪定対象]]]
[[[http://scp-jp.wikidot.com/video-log-of-scp-1779-jp/tags/+%E5%90%88%E4%BD%9C%E8%A8%98%E4%BA%8B%E5%89%AA%E5%AE%9A%E9%80%9A%E7%9F%A5|映像記録SCP-1779-JP-B剪定対象]]]
[[[http://scp-jp.wikidot.com/scp-poem/tags/+%E5%90%88%E4%BD%9C%E8%A8%98%E4%BA%8B%E5%89%AA%E5%AE%9A%E9%80%9A%E7%9F%A5|SCP詩集剪定対象]]]
[[[http://scp-jp.wikidot.com/log-of-unexplained-locations-jp/tags/+%E5%90%88%E4%BD%9C%E8%A8%98%E4%BA%8B%E5%89%AA%E5%AE%9A%E9%80%9A%E7%9F%A5|未解明領域記録-JP剪定対象]]]
[[[http://scp-jp.wikidot.com/scp-flavor/tags/+%E5%90%88%E4%BD%9C%E8%A8%98%E4%BA%8B%E5%89%AA%E5%AE%9A%E9%80%9A%E7%9F%A5|SCPフレーバーテキスト集剪定対象]]]
※リンク先に剪定対象が存在しないこともあります。"""

    if dry_run:
        logger.info("フォーラム投稿:")
        logger.info(f"  スレッドID: {FORUM_THREAD_ID}")
        logger.info(f"  件名: {title}")
        logger.info(f"  内容:\n{source}")
        return {"posted": True, "title": title, "dry_run": True}

    try:
        thread = site.get_thread(FORUM_THREAD_ID)
        thread.reply(source=source, title=title)
        logger.info(f"フォーラム投稿完了: {title}")
        return {"posted": True, "title": title}
    except Exception as e:
        logger.error(f"Error posting forum notice: {e}")
        return {"posted": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="剪定通知タグ付与スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="実際の変更を行わずに対象を表示")
    args = parser.parse_args()

    load_dotenv()
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    results = {"processed": [], "errors": [], "forum": None}

    if args.dry_run:
        logger.info("=== DRY-RUN MODE ===")

    with wikidot.Client(
        username=os.environ["WIKIDOT_USERNAME"],
        password=os.environ["WIKIDOT_PASSWORD"],
    ) as client:
        site = client.site.get("scp-jp")

        for category in COLLAB_CATEGORIES:
            # rating <= -3 かつ通知タグなしのページを検索
            pages = site.pages.search(
                category=category,
                rating="<=-3",
                tags=[f"-{NOTICE_TAG}"]
            )

            for page in pages:
                try:
                    if args.dry_run:
                        logger.info(f"[DRY-RUN] {page.fullname} (rating: {page.rating}): +[{NOTICE_TAG}]")
                    else:
                        page.tags.append(NOTICE_TAG)
                        page.commit_tags()
                        logger.info(f"{page.fullname} (rating: {page.rating}): +[{NOTICE_TAG}]")

                    results["processed"].append(
                        {"page": page.fullname, "rating": page.rating}
                    )
                except Exception as e:
                    logger.error(f"Error processing page {page.fullname}: {e}")
                    results["errors"].append({"page": page.fullname, "error": str(e)})

        # フォーラム投稿（処理対象がある場合のみ）
        if results["processed"]:
            results["forum"] = post_forum_notice(site, dry_run=args.dry_run)

    # Discord通知（dry-run時は送信しない）
    if args.dry_run:
        logger.info("=== SUMMARY ===")
        logger.info(f"処理対象: {len(results['processed'])}件")
        logger.info(f"エラー: {len(results['errors'])}件")
        if results["forum"]:
            logger.info(f"フォーラム投稿: {'予定' if results['forum'].get('posted') else 'なし'}")
        return

    processed_list = "\n".join(
        [
            f"- {p['page']} (rating: {p['rating']})"
            for p in results["processed"][:10]
        ]
    )
    if len(results["processed"]) > 10:
        processed_list += f"\n...他 {len(results['processed']) - 10}件"

    fields = [
        {
            "name": "剪定通知タグ付与",
            "value": f"処理: {len(results['processed'])}件\nエラー: {len(results['errors'])}件",
            "inline": False,
        }
    ]

    if results["processed"]:
        fields.append(
            {
                "name": "対象ページ",
                "value": processed_list or "なし",
                "inline": False,
            }
        )

    if results["forum"]:
        forum_status = "投稿済み" if results["forum"].get("posted") else f"失敗: {results['forum'].get('error', '不明')}"
        fields.append(
            {
                "name": "フォーラム通知",
                "value": forum_status,
                "inline": False,
            }
        )

    if results["errors"] or (results["forum"] and not results["forum"].get("posted")):
        color = COLOR_ERROR
    else:
        color = COLOR_SUCCESS

    send_discord_notification(
        webhook_url=webhook_url,
        title="collab_deletion/notice 完了",
        description=f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        fields=fields,
        color=color,
    )


if __name__ == "__main__":
    main()
