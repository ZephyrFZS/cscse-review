#!/usr/bin/env python3
"""Gate for step 7: every mapping code must appear in allowed source codes.

Usage:
  python check_consistency.py case.yaml --allowed CODE1,CODE2,BUNDLE1
  python check_consistency.py case.yaml --allowed-file transcript_codes.txt

Exit 0 if OK; 1 if conflicts. Also flags grades in statement text.
CODES 须来自成绩单/录取转学分原文，勿使用与申请人无关的示例课号入库。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


GRADE_RE = re.compile(
    r"(平均成绩|High Distinction|\bHD\b|\bDN\b|\bCR\b|\bPS\b|\d{2,3}\s*分)"
)
BANNED_RE = re.compile(
    r"(高度一致|完全等同|大部分课程均能对应|整体相符|认定成功|保证通过|"
    r"确保能报名|解决报考资格|证书将显示代码|强对应|中对应|弱对应|"
    r"QS\s*排名|QS\s*前|名校背书)"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_yaml")
    ap.add_argument("--allowed", default="")
    ap.add_argument("--allowed-file", default="")
    args = ap.parse_args()
    case = yaml.safe_load(Path(args.case_yaml).read_text(encoding="utf-8"))
    allowed = {x.strip() for x in args.allowed.split(",") if x.strip()}
    if args.allowed_file:
        allowed |= {
            ln.strip()
            for ln in Path(args.allowed_file).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        }
    if not allowed:
        print("ERROR: provide --allowed or --allowed-file with transcript/offer codes", file=sys.stderr)
        sys.exit(2)

    errors = []
    for m in case.get("mappings") or []:
        code = (m.get("code") or "").strip()
        mode = m.get("mode") or ""
        if not code:
            continue
        if code not in allowed:
            if "对照" in mode or "打包" in mode:
                errors.append(
                    f"WARN-as-error: {code} not in transcript/offer; mode={mode!r}. "
                    f"Use the bundled catalogue code from the transcript/offer as code; "
                    f"put specific course对照 only in desc."
                )
            else:
                errors.append(f"MISSING: {code} not found in allowed source codes")

    stmt = case.get("personal_statement") or ""
    reason = case.get("review_reason") or ""
    for label, text in [("personal_statement", stmt), ("review_reason", reason)]:
        if GRADE_RE.search(text):
            errors.append(f"GRADES: possible grade language in {label}")
        if BANNED_RE.search(text):
            errors.append(f"BANNED: disallowed wording in {label} (see templates.md)")

    if errors:
        print("FAIL")
        for e in errors:
            print("-", e)
        sys.exit(1)
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
