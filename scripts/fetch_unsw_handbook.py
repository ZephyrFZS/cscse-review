#!/usr/bin/env python3
"""EXAMPLE ONLY: Fetch UNSW handbook JSON from __NEXT_DATA__.

For other universities, see ../course-sources.md — do not assume this pattern.

Usage:
  python fetch_unsw_handbook.py course COURSECODE 2026
  python fetch_unsw_handbook.py courses CODE1,CODE2 2025 -o courses.json
  python fetch_unsw_handbook.py program PROGRAMCODE 2025

COURSECODE / PROGRAMCODE 换成成绩单或 handbook 上的真实代码；下列仅为该校抓取方式示例。
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import subprocess
import sys
from pathlib import Path


def fetch_html(url: str) -> str:
    r = subprocess.run(
        ["curl", "-sL", "-A", "Mozilla/5.0", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"curl failed for {url}: {r.stderr}")
    return r.stdout


def page_content(url: str) -> dict:
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        fetch_html(url),
        re.S,
    )
    if not m:
        raise RuntimeError(f"No __NEXT_DATA__ in {url}")
    return json.loads(m.group(1))["props"]["pageProps"]["pageContent"]


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def course_record(code: str, year: str) -> dict:
    url = f"https://www.handbook.unsw.edu.au/postgraduate/courses/{year}/{code}"
    p = page_content(url)
    lo = p.get("unit_learning_outcomes")
    if isinstance(lo, str):
        try:
            lo = json.loads(lo)
        except json.JSONDecodeError:
            lo = []
    outcomes = []
    if isinstance(lo, list):
        outcomes = [strip_html(x.get("description")) for x in lo if isinstance(x, dict)]
    return {
        "code": code,
        "year": year,
        "title": p.get("title"),
        "uoc": p.get("credit_points"),
        "desc": strip_html(p.get("description")),
        "outcomes": outcomes,
        "url": url,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c1 = sub.add_parser("course", help="one course")
    c1.add_argument("code")
    c1.add_argument("year")

    c2 = sub.add_parser("courses", help="comma-separated courses → JSON")
    c2.add_argument("codes")
    c2.add_argument("year")
    c2.add_argument("-o", "--output", default="courses.json")

    p1 = sub.add_parser("program", help="program page raw pageContent keys summary")
    p1.add_argument("code")
    p1.add_argument("year")

    args = ap.parse_args()
    if args.cmd == "course":
        print(json.dumps(course_record(args.code, args.year), ensure_ascii=False, indent=2))
    elif args.cmd == "courses":
        out = {}
        for code in [x.strip() for x in args.codes.split(",") if x.strip()]:
            try:
                out[code] = course_record(code, args.year)
                print(code, "ok", out[code]["title"], file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(code, "FAIL", e, file=sys.stderr)
        Path(args.output).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("wrote", args.output)
    elif args.cmd == "program":
        url = f"https://www.handbook.unsw.edu.au/postgraduate/programs/{args.year}/{args.code}"
        p = page_content(url)
        print(
            json.dumps(
                {
                    "title": p.get("title"),
                    "credit_points": p.get("credit_points"),
                    "asced_broad": p.get("asced_broad"),
                    "description": strip_html(p.get("description"))[:2000],
                    "url": url,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
