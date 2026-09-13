#!/usr/bin/env python3
"""
コンテスト参加記事の評価スナップショット (read-only)

pages.search (ListPages) の rating と、WhoRatedPageModule から得た評価内訳の合計を
突き合わせる。ListPages は内部キャッシュで反映が遅れるため、内訳側を検算に使う。

出力 (--out-dir):
  summary_<ts>.csv  記事ごとの search 値 / 内訳合計 / 差分
  votes_<ts>.json   記事ごとの投票者と票
"""

import argparse
import csv
import json
import os
from datetime import datetime, timedelta, timezone

import re
from urllib.parse import quote

import httpx
import wikidot
from bs4 import BeautifulSoup
from wikidot.module.page import PageCollection

JST = timezone(timedelta(hours=9))
# ハブの部門別 ListPages に合わせる
def log(msg: str) -> None:
    print(f"[{datetime.now(JST):%H:%M:%S}] {msg}", flush=True)


DIVISION_TAGS = {"scp": "夢想", "goi-format": "泡影", "tale": "陶酔"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="scp-jp")
    ap.add_argument("--tag", default="夢コン26")
    ap.add_argument("--exclude-tag", default="コンテスト")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    ts = datetime.now(JST)
    stamp = ts.strftime("%Y%m%d_%H%M%S")
    os.makedirs(args.out_dir, exist_ok=True)

    with wikidot.Client() as client:
        site = client.site.get(args.site)
        log(f"search start ({ts.isoformat()})")
        pages = site.pages.search(category="_default", tags=f"+{args.tag} -{args.exclude_tag}")
        log(f"search done: {len(pages)} pages")
        chunk = 10
        for i in range(0, len(pages), chunk):
            PageCollection._acquire_page_votes(site, pages[i:i + chunk])
            log(f"votes {min(i + chunk, len(pages))}/{len(pages)}")

        rows, detail = [], []
        for p in pages:
            votes = list(p.votes)
            plus = sum(1 for v in votes if v.value > 0)
            minus = sum(1 for v in votes if v.value < 0)
            total = sum(v.value for v in votes)
            division = [name for t, name in DIVISION_TAGS.items() if t in p.tags]
            rows.append({
                "division": "/".join(division) or "-",
                "fullname": p.fullname,
                "title": p.title,
                "author": p.created_by.name if p.created_by else "",
                "search_rating": p.rating,
                "search_votes": p.votes_count,
                "calc_rating": total,
                "calc_plus": plus,
                "calc_minus": minus,
                "calc_votes": len(votes),
                "diff": total - p.rating,
                "event1": "_イベント1" in p.tags,
            })
            detail.append({
                "fullname": p.fullname,
                "votes": [{"user": v.user.name if v.user else None, "value": v.value} for v in votes],
            })

        # search と別経路 (タグページ) の記事集合を突き合わせ、search から漏れた記事の内訳を個別に取る
        searched = {p.fullname for p in pages}
        tag_url = f"http://{args.site}.wikidot.com/system:page-tags/tag/{quote(args.tag)}"
        soup = BeautifulSoup(httpx.get(tag_url, follow_redirects=True, timeout=60).text, "lxml")
        tagged = {a["href"].lstrip("/") for item in soup.select(".list-pages-item") for a in item.select("a[href^='/']")}
        missing = sorted(fn for fn in tagged if ":" not in fn and fn not in searched)
        log(f"tagpage cross-check: {len(missing)} candidates")
        for fn in missing:
            resp = httpx.get(f"http://{args.site}.wikidot.com/{fn}", follow_redirects=True, timeout=60)
            page_html = resp.text
            if f"/system:page-tags/tag/{quote(args.exclude_tag)}" in page_html:
                continue
            m = re.search(r"WIKIREQUEST\.info\.pageId\s*=\s*(\d+)\s*;", page_html)
            if resp.status_code != 200 or not m:
                # タグページ側の残骸 (削除済み等)。黙って落とさず行として残す
                rows.append({
                    "division": f"HTTP{resp.status_code}", "fullname": fn, "title": "", "author": "",
                    "search_rating": "", "search_votes": "", "calc_rating": 0,
                    "calc_plus": 0, "calc_minus": 0, "calc_votes": 0, "diff": "", "event1": "",
                })
                continue
            body = site.amc_request([{"moduleName": "pagerate/WhoRatedPageModule", "pageId": int(m.group(1))}])[0].json()["body"]
            vals = [1 if s.text.strip() == "+" else -1 if s.text.strip() == "-" else int(s.text.strip())
                    for s in BeautifulSoup(body, "lxml").select("span[style^='color']")]
            rows.append({
                "division": "search未反映", "fullname": fn, "title": "", "author": "",
                "search_rating": "", "search_votes": "", "calc_rating": sum(vals),
                "calc_plus": vals.count(1), "calc_minus": vals.count(-1), "calc_votes": len(vals),
                "diff": "", "event1": "",
            })
        print(f"search={len(searched)} tagpage_links={len(tagged)} missing_in_search={missing}")

    rows.sort(key=lambda r: (r["division"], -r["calc_rating"]))
    with open(f"{args.out_dir}/summary_{stamp}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(f"{args.out_dir}/votes_{stamp}.json", "w", encoding="utf-8") as f:
        json.dump({"taken_at": ts.isoformat(), "pages": detail}, f, ensure_ascii=False, indent=1)

    print(f"taken_at={ts.isoformat()} pages={len(rows)}")
    for r in rows:
        mark = "" if r["diff"] in (0, "") else f"  <-- diff {r['diff']:+d}"
        print(f"{r['division']:6} {r['calc_rating']:+4d} (+{r['calc_plus']}/-{r['calc_minus']}) search={r['search_rating']} {r['fullname']} {r['title']}{mark}")


if __name__ == "__main__":
    main()
