#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "wikidot>=4.0.1,<5",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
SCP-4000-JPコンテスト終了に伴うリネーム・編集スクリプト

入力: TSV形式（最終ナンバー割当, ページ名）
処理:
  1. ページをscp-<num>-jpにリネーム
  2. タイトルが"SCP-4000-JP - xxx"形式の場合、"SCP-<num>-JP"に変更
  3. ソース内のSCP-4000-JP/scp-4000-jpを置換
"""

import argparse
import difflib
import logging
import os
import re
import sys
from dotenv import load_dotenv
import wikidot

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TITLE_PATTERN = re.compile(r"^SCP-4000-JP - .+$")


def parse_input(lines: list[str]) -> dict[str, str]:
    """TSVデータをパースして {ページ名: ナンバー} の辞書を返す"""
    mapping = {}
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        # ヘッダ行をスキップ
        if i == 0 and "ページ名" in line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            num = parts[0].strip()
            page_name = parts[1].strip()
            if num and page_name:
                mapping[page_name] = num
    return mapping


def generate_diff(old_text: str, new_text: str, filename: str) -> str:
    """差分を生成"""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}")
    return "".join(diff)


# fragment:scp-4000-jp-xxx パターン（置換から除外）
FRAGMENT_PATTERN = re.compile(r"(fragment:)(scp-4000-jp-[a-z0-9-]+)")


def replace_source(source: str, new_num: str, mapping: dict[str, str]) -> str:
    """
    ソース置換を行う

    Args:
        source: 元のソース
        new_num: 現在のページの新ナンバー
        mapping: {fullname: num} の辞書（全エントリ）

    Returns:
        置換後のソース
    """
    lines = source.split("\n")
    result_lines = []

    # fullname置換用のプレースホルダを事前に生成
    fullname_placeholders = {}
    for i, (old_fullname, target_num) in enumerate(mapping.items()):
        new_fullname = f"scp-{target_num}-jp"
        placeholder = f"__FULLNAME_PH_{i}__"
        fullname_placeholders[old_fullname] = (placeholder, new_fullname)

    for line in lines:
        # 1. 除外: local--filesを含む行はスキップ
        if "local--files/" in line:
            result_lines.append(line)
            continue

        new_line = line

        # 2. fragment:を含む部分は保護（一時的にプレースホルダに置換）
        fragment_matches = FRAGMENT_PATTERN.findall(new_line)
        fragment_placeholders = {}
        for i, (prefix, fullname) in enumerate(fragment_matches):
            placeholder = f"__FRAGMENT_PH_{i}__"
            fragment_placeholders[placeholder] = f"{prefix}{fullname}"
            new_line = new_line.replace(f"{prefix}{fullname}", placeholder, 1)

        # 3. fullname置換: 全ての4000-JP記事のfullnameをプレースホルダに置換
        for old_fullname, (placeholder, _) in fullname_placeholders.items():
            new_line = new_line.replace(old_fullname, placeholder)

        # 4. 汎用置換（残りの4000-JP/4000-jp）
        # 前に数字がない場合のみ置換（14000-JPのような誤置換を防ぐ）
        new_line = re.sub(r"(?<![0-9])4000-JP", f"{new_num}-JP", new_line)
        new_line = re.sub(r"(?<![0-9])4000-jp", f"{new_num}-jp", new_line)

        # 5. プレースホルダを元に戻す（fullname）
        for old_fullname, (placeholder, new_fullname) in fullname_placeholders.items():
            new_line = new_line.replace(placeholder, new_fullname)

        # 6. プレースホルダを元に戻す（fragment）
        for placeholder, original in fragment_placeholders.items():
            new_line = new_line.replace(placeholder, original)

        result_lines.append(new_line)

    return "\n".join(result_lines)


def process_page(page, num: str, mapping: dict[str, str], dry_run: bool) -> dict:
    """ページを処理"""
    result = {
        "fullname": page.fullname,
        "num": num,
        "actions": [],
        "diffs": [],
    }

    new_fullname = f"scp-{num}-jp"

    # リネーム
    result["actions"].append(f"リネーム: {page.fullname} -> {new_fullname}")

    # num == "4000" の場合はリネームのみ
    if num == "4000":
        if not dry_run:
            page.rename(new_fullname)
        return result

    # タイトル変更判定
    new_title = None
    if TITLE_PATTERN.match(page.title):
        new_title = f"SCP-{num}-JP"
        result["actions"].append(f"タイトル変更: {page.title} -> {new_title}")

    # ソース置換
    old_source = page.source.wiki_text
    new_source = replace_source(old_source, num, mapping)

    source_changed = old_source != new_source
    if source_changed:
        diff = generate_diff(old_source, new_source, page.fullname)
        result["diffs"].append(diff)
        result["actions"].append("ソース置換: SCP-4000-JP -> SCP-{}-JP, scp-4000-jp -> scp-{}-jp".format(num, num))

    if not dry_run:
        # リネーム実行
        page = page.rename(new_fullname)

        # 編集実行（タイトルまたはソースが変更される場合）
        if new_title or source_changed:
            comment = f"SCP-4000-JPコンテスト終了に伴う編集（割当: SCP-{num}-JP）"
            page.edit(
                title=new_title,
                source=new_source if source_changed else None,
                comment=comment,
                force_edit=True
            )

    return result


def main():
    parser = argparse.ArgumentParser(description="SCP-4000-JPコンテスト終了に伴うリネーム・編集")
    parser.add_argument("--dry-run", action="store_true", help="実際の変更を行わずに対象と差分を表示")
    parser.add_argument("--input", type=str, help="入力TSVファイル（省略時はstdinから読み込み）")
    args = parser.parse_args()

    load_dotenv()

    # 入力読み込み
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    mapping = parse_input(lines)
    logger.info(f"入力データ: {len(mapping)}件")

    if args.dry_run:
        logger.info("=" * 60)
        logger.info("DRY-RUN MODE")
        logger.info("=" * 60)

    results = {"processed": [], "skipped": [], "errors": []}

    with wikidot.Client(
        username=os.environ["WIKIDOT_USERNAME"],
        password=os.environ["WIKIDOT_PASSWORD"],
    ) as client:
        site = client.site.get("scp-jp")

        # ページ検索
        logger.info("ページを検索中...")
        pages = site.pages.search(category="_default", tags=["+4000jp", "-ハブ"])
        logger.info(f"検索結果: {len(pages)}件")

        # PageIDをバルク取得
        logger.info("PageIDを取得中...")
        pages.get_page_ids()

        # 各ページを処理
        interactive = not args.dry_run  # dry-runでなければ対話モード
        bypass = False  # bypass入力後はTrue

        for page in pages:
            if page.fullname not in mapping:
                results["skipped"].append(page.fullname)
                continue

            num = mapping[page.fullname]

            try:
                result = process_page(page, num, mapping, args.dry_run)
                results["processed"].append(result)

                # ログ出力
                logger.info("-" * 60)
                logger.info(f"[{page.fullname}] -> SCP-{num}-JP")
                for action in result["actions"]:
                    logger.info(f"  {action}")
                for diff in result["diffs"]:
                    print(diff)

                # 対話モード: 1ページずつ確認
                if interactive and not bypass:
                    user_input = input("\n[Enter: 次へ / bypass: 以降スキップなし] > ").strip().lower()
                    if user_input == "bypass":
                        bypass = True
                        logger.info("以降のページは確認なしで処理します")

            except Exception as e:
                logger.exception(f"エラー: {page.fullname}: {e}")
                results["errors"].append({"page": page.fullname, "error": str(e)})

    # サマリー
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"処理: {len(results['processed'])}件")
    logger.info(f"スキップ（マッピングなし）: {len(results['skipped'])}件")
    logger.info(f"エラー: {len(results['errors'])}件")

    if results["errors"]:
        logger.info("エラー詳細:")
        for err in results["errors"]:
            logger.info(f"  {err['page']}: {err['error']}")


if __name__ == "__main__":
    main()
