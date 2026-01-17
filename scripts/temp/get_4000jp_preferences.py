#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "wikidot>=4.0.1,<5",
# ]
# ///
"""
SCP-4000-JPコンテスト希望順位取得スクリプト

各参加ページのディスカッションから最初のポストを取得し、
希望順位を出力する。
"""

import logging
import re
from typing import TypedDict

import wikidot
from wikidot.module.forum_post import ForumPostCollection
from wikidot.module.forum_thread import ForumThreadCollection

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PreferenceResult(TypedDict):
    """希望順位のパース結果"""

    preferences: dict[str, str]  # {"1": "4999", "2": "4444", ...}
    ambiguous: dict[str, str]  # {"3": "4X00最小", ...} 曖昧表現
    notes: list[str]  # 追加の注釈


def parse_preferences(html_text: str) -> PreferenceResult:
    """
    フォーラムポストのHTMLから希望順位をパースする。

    Args:
        html_text: フォーラムポストのHTML

    Returns:
        PreferenceResult: パース結果
            - preferences: 確定した希望順位 {"1": "4999", "2": "4444", ...}
            - ambiguous: 曖昧な表現 {"3": "4X00最小", ...}
            - notes: 追加の注釈

    パターン対応:
        1. 標準形式: 第N希望: SCP-XXXX-JP
        2. boldタグ付き形式: <strong>第N希望:</strong> SCP-XXXX-JP
        3. コロンなし形式: N: XXXX
        4. 曖昧表現: 4X00最小, 411X最小 など
        5. 第6希望以降の表現
    """
    result: PreferenceResult = {"preferences": {}, "ambiguous": {}, "notes": []}

    # HTMLタグを適切に処理（<br/>を改行に変換）
    text = html_text.replace("<br/>", "\n").replace("<br>", "\n")

    # パターン1: 標準形式 「第N希望: SCP-XXXX-JP」
    # <strong>タグがある場合とない場合の両方に対応
    # <span>タグで装飾されている場合も対応
    # コロンの位置は </strong> の前後どちらでも対応
    # 「第0希望」は無視（全員共通のため）
    pattern_standard = re.compile(
        r"(?:<strong>)?第([1-5])希望(?::</strong>|</strong>:?|:)\s*(?:<[^>]+>)*\s*(?:SCP-)?(\d{4})(?:-JP)?",
        re.IGNORECASE,
    )
    for match in pattern_standard.finditer(text):
        rank = match.group(1)
        number = match.group(2)
        result["preferences"][rank] = number

    # パターン2: コロンなし形式 「N: XXXX」（番号希望形式）
    # 例: 0: 4000, 1: 4444
    pattern_colon = re.compile(r"(?:^|\n)\s*([1-5])\s*:\s*(\d{4})", re.MULTILINE)
    for match in pattern_colon.finditer(text):
        rank = match.group(1)
        number = match.group(2)
        if rank not in result["preferences"]:  # 標準形式で見つからなかった場合のみ
            result["preferences"][rank] = number

    # パターン3: 曖昧表現の検出
    # 「4X00最小」「411X最小」「4X00(Xは残存の中で最も小さい数字)」など
    pattern_ambiguous = re.compile(
        r"第([1-5])希望[:\s]*(?:SCP-)?([4X\d]+)(?:-JP)?[^<\n]*(?:最小|最も[小若]|残存)",
        re.IGNORECASE,
    )
    for match in pattern_ambiguous.finditer(text):
        rank = match.group(1)
        ambiguous_expr = match.group(2)
        if "X" in ambiguous_expr.upper() or "x" in ambiguous_expr:
            result["ambiguous"][rank] = ambiguous_expr

    # パターン4: 特殊パターン「第N希望～: ...」の形式
    # 例: 「第2希望～: 利用可能なSCP-411X-JPのうち最も若い番号」
    pattern_range = re.compile(
        r"第([1-5])希望[～~〜以降]*[:\s]*([^\n<]+(?:最小|最も[小若]|残存)[^\n<]*)",
        re.IGNORECASE,
    )
    for match in pattern_range.finditer(text):
        rank = match.group(1)
        expr = match.group(2).strip()
        # 4桁の数字パターンを抽出
        number_match = re.search(r"(\d{4})", expr)
        if number_match:
            # 確定番号がある場合
            if rank not in result["preferences"]:
                result["preferences"][rank] = number_match.group(1)
        else:
            # 曖昧表現として記録
            pattern_x = re.search(r"(4[X\d]{3})", expr, re.IGNORECASE)
            if pattern_x and rank not in result["ambiguous"]:
                result["ambiguous"][rank] = expr

    # パターン5: 第6希望以降の注釈を検出
    if re.search(r"第[6-9]希望|以下[、,].+(?:残存|希望)", text):
        note_match = re.search(r"以下[、,]([^\n<]+)", text)
        if note_match:
            result["notes"].append(note_match.group(1).strip())

    # パターン6: stellationnovaさんの特殊形式
    # 「3: 4X00(Xは残存の中で最も小さい数字)」
    pattern_special = re.compile(
        r"([1-5])\s*:\s*4([Xx])00\s*\([^)]+\)",
        re.IGNORECASE,
    )
    for match in pattern_special.finditer(text):
        rank = match.group(1)
        if rank not in result["preferences"] and rank not in result["ambiguous"]:
            result["ambiguous"][rank] = "4X00最小"

    # パターン7: witheriteさんの特殊形式
    # 「第2希望～: 利用可能なSCP-411X-JPのうち最も若い番号」
    witherite_pattern = re.search(
        r"利用可能な.*?(4\d{2}[Xx]).*?最も若い",
        text,
        re.IGNORECASE,
    )
    if witherite_pattern:
        ambiguous_num = witherite_pattern.group(1)
        # どの希望順位かを特定
        context_match = re.search(
            r"第([1-5])希望[～~〜以降]*[:\s]*利用可能",
            text,
            re.IGNORECASE,
        )
        if context_match:
            rank = context_match.group(1)
            if rank not in result["ambiguous"]:
                result["ambiguous"][rank] = f"{ambiguous_num}最小"

    return result


def main():
    logger.info("SCP-4000-JP希望順位取得スクリプト開始")

    # ログインなしでクライアント作成
    with wikidot.Client() as client:
        site = client.site.get("scp-jp")

        # ページ検索
        logger.info("ページを検索中...")
        pages = site.pages.search(category="_default", tags=["+4000jp", "-ハブ"])
        logger.info(f"検索結果: {len(pages)}件")

        # ページIDをバルク取得
        logger.info("ページIDを取得中...")
        pages.get_page_ids()

        # scp-4000-jp（プレースホルダ）を除外
        pages = [p for p in pages if p.fullname != "scp-4000-jp"]
        logger.info(f"プレースホルダ除外後: {len(pages)}件")

        # ForumCommentsListModuleをバルク呼び出し
        logger.info("ディスカッションスレッドIDを取得中...")
        responses = site.amc_request(
            [{"moduleName": "forum/ForumCommentsListModule", "pageId": page.id} for page in pages]
        )

        # thread_idを抽出
        thread_ids = []
        page_thread_map = {}  # {thread_id: page}
        for page, response in zip(pages, responses, strict=True):
            body = response.json()["body"]
            match = re.search(r"WIKIDOT\.forumThreadId = (\d+);", body)
            if match:
                thread_id = int(match.group(1))
                thread_ids.append(thread_id)
                page_thread_map[thread_id] = page
            else:
                logger.warning(f"ディスカッションなし: {page.fullname}")

        logger.info(f"スレッド数: {len(thread_ids)}件")

        # スレッドをバルク取得
        logger.info("スレッドを取得中...")
        threads = ForumThreadCollection.acquire_from_thread_ids(site, thread_ids)

        # ポストをバルク取得
        logger.info("ポストを取得中...")
        posts_dict = ForumPostCollection.acquire_all_in_threads(list(threads))

        # 最初のポストのみ抽出
        first_posts = []
        for thread_id, posts in posts_dict.items():
            if posts:
                first_post = min(posts, key=lambda p: p.id)  # 最小IDが最初のポスト
                first_posts.append((page_thread_map[thread_id], first_post))

        logger.info(f"最初のポスト数: {len(first_posts)}件")

        # パース結果を収集
        all_results: dict[str, PreferenceResult] = {}

        for page, post in sorted(first_posts, key=lambda x: x[0].fullname):
            pref_result = parse_preferences(post.text)
            all_results[page.fullname] = pref_result

        # 出力（TSV形式: ページ名 \t 第1 / 第2 / 第3 / 第4 / 第5）
        print("ページ名\t希望順位")
        for page_name, pref_result in sorted(all_results.items()):
            prefs = []
            for rank in ["1", "2", "3", "4", "5"]:
                if rank in pref_result["preferences"]:
                    prefs.append(pref_result["preferences"][rank])
                elif rank in pref_result["ambiguous"]:
                    prefs.append(pref_result["ambiguous"][rank])
                else:
                    prefs.append("")
            print(f"{page_name}\t{' / '.join(prefs)}")


if __name__ == "__main__":
    main()
