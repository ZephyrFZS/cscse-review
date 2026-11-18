#!/usr/bin/env python3
"""cscse-review skill fixture tests (happy + boundary).

Run:
  python3 run_skill_tests.py
  python3 run_skill_tests.py -v
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "check_consistency.py"
FIX = Path(__file__).resolve().parent / "fixtures"

# 测试用白名单（J3）：仅测用，非教育部完整目录；生产须对最新公示全文
KNOWN_GRAD_CODES = {
    "0812": "计算机科学与技术",
    "0835": "软件工程",
    "0839": "网络空间安全",
    "0854": "电子信息",  # 专业学位类别
    "0202": "应用经济学",
    "0251": "金融",  # * 仅硕士
    "1201": "管理科学与工程",
    "0714": "统计学",
    "0401": "教育学",
}
# 研究生目录说明：名称后加 * 仅可授硕士专业学位（此处列出测试用子集）
MASTER_ONLY_STAR = {"0251", "0252", "0253", "0151", "0454", "1054"}

KNOWN_UG_CODES = {
    "080901": "计算机科学与技术",
    "080902": "软件工程",
    "020301K": "金融学",
}

GRADE_RE = re.compile(
    r"(平均成绩|High Distinction|\bHD\b|\bDN\b|\bCR\b|\bPS\b|\d{2,3}\s*分)"
)
BANNED_RE = re.compile(
    r"(高度一致|完全等同|大部分课程均能对应|整体相符|认定成功|保证通过|"
    r"确保能报名|解决报考资格|证书将显示代码|强对应|中对应|弱对应|"
    r"QS\s*排名|QS\s*前|名校背书)"
)


def normalize_level(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("本科") or s == "学士":
        return "本科"
    if s.startswith("硕士"):
        return "硕士"
    if s.startswith("博士"):
        return "博士"
    return s


def validate_case(case: dict) -> list[str]:
    errs: list[str] = []
    level = normalize_level(case.get("degree_level", ""))
    if level not in {"本科", "硕士", "博士"}:
        errs.append("degree_level: missing or invalid")

    if not (case.get("catalogue_source") or "").strip():
        errs.append("catalogue_source: empty (第2步禁止无来源写代码)")

    if case.get("cert_within_12_months") is False:
        errs.append("window_12m: 超过12个月，应先走开通通道，不进入常规生成")

    req = case.get("request") or {}
    code = str(req.get("discipline_code") or "").strip()
    name = str(req.get("discipline") or "").strip()
    if code:
        if level == "本科":
            known = KNOWN_UG_CODES
        else:
            known = KNOWN_GRAD_CODES
        if code not in known:
            errs.append(f"catalogue_code: {code} 不在测试白名单/疑似臆造，须对照教育部目录")
        else:
            official = known[code]
            # 允许名称以官方全称为前缀或相等；专硕类别名「电子信息」等
            if name and official not in name and name not in official:
                errs.append(
                    f"catalogue_name: 代码 {code} 官方名为「{official}」，当前写「{name}」不一致"
                )

    if level == "博士" and code in MASTER_ONLY_STAR:
        errs.append(f"phd_star_category: {code} 为仅可授硕士的专业学位类别(*)，不可作博士目标")

    # 国内方案层次
    for d in case.get("domestic") or []:
        dlev = normalize_level(d.get("level", ""))
        if dlev and dlev != level:
            errs.append(f"level_mismatch: degree_level={level} 但国内方案 level={dlev}")
        plan_code = str(d.get("plan_code") or "").strip()
        dtype = str(req.get("degree_type") or "")
        if level == "硕士" and dtype == "学硕" and plan_code.startswith("085"):
            errs.append("degree_type_mix: 学硕诉求却使用专硕方案代码(085x)")
        if level == "硕士" and dtype == "专硕" and plan_code and plan_code.startswith("081") and not plan_code.startswith("085"):
            # soft: 0812 academic vs 0854 professional
            if plan_code == "0812":
                errs.append("degree_type_mix: 专硕诉求却使用学硕一级学科方案")

    # 映射强度
    for m in case.get("mappings") or []:
        strength = (m.get("strength") or "").strip()
        cell = str(m.get("domestic_0") or "").strip()
        if strength in {"弱", "无"} and cell and cell not in {"—", "-", "－"}:
            errs.append(f"weak_mapping: strength={strength} 但 domestic_0={cell!r}（应写—）")
        cat = (m.get("category") or "").strip()
        if level == "本科" and cat == "通识" and strength in {"强", "中"} and cell not in {"—", "-", "－", ""}:
            errs.append(f"ge_forced: 通识课不应强行专业核心对应 → {cell!r}")

    # 学分（硕士强制；本/博若提供则核对）
    cs, cr = case.get("credit_sum"), case.get("credit_required")
    if cs is not None and cr is not None and cs != cr:
        if level == "硕士" or case.get("enforce_credits", True):
            errs.append(f"credits: credit_sum={cs} != credit_required={cr}")

    # 博士空壳
    if level == "博士":
        modules = case.get("modules") or []
        maps = case.get("mappings") or []
        if len(maps) <= 2 and not modules:
            errs.append("phd_shell: 授课很少且无培养环节对照")

    # 成绩语言（双保险；check_consistency 也会查）
    for label in ("personal_statement", "review_reason"):
        text = case.get(label) or ""
        if GRADE_RE.search(text):
            errs.append(f"grades: {label} 含成绩表述")
        if BANNED_RE.search(text):
            errs.append(f"banned_words: {label} 含 templates 禁用表述")

    return errs


def run_check_consistency(case: dict) -> list[str]:
    allowed = case.get("allowed_codes") or []
    if not allowed:
        return ["transcript_setup: fixture 缺少 allowed_codes"]
    # write temp case without test-only keys that confuse nothing — script only reads mappings/statements
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "mappings": case.get("mappings") or [],
                "personal_statement": case.get("personal_statement") or "",
                "review_reason": case.get("review_reason") or "",
            },
            f,
            allow_unicode=True,
        )
        path = f.name
    proc = subprocess.run(
        [sys.executable, str(CHECK), path, "--allowed", ",".join(allowed)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return []
    out = (proc.stdout or "") + (proc.stderr or "")
    errs = []
    for line in out.splitlines():
        if line.startswith("- "):
            errs.append("transcript_code: " + line[2:])
        elif line.startswith("FAIL") or line.startswith("ERROR"):
            continue
    if proc.returncode != 0 and not errs:
        errs.append(f"transcript_code: check_consistency exit={proc.returncode} {out.strip()}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", action="store_true")
    args = ap.parse_args()

    # 静态：skill 文本须含关键闸门表述
    skill = (ROOT.parent / "SKILL.md").read_text(encoding="utf-8")
    static_checks = [
        ("ask_user_on_miss", "匹配不到就向用户要" in skill or "立刻停" in skill),
        ("degree_lock", "degree_level" in skill and "本科/学士" in skill),
        ("no_hallucination_catalogue", "禁止" in skill and "目录" in skill),
        ("codex_claude", "Codex" in skill and "Claude" in skill),
        ("scope_major_only", "专业领域" in skill and "不覆盖" in skill),
        ("no_overclaim", "不保证" in skill and "申请" in skill),
        ("ban_高度一致_rule", "高度一致" not in skill or "禁用「高度一致」" in skill),
        ("c1_transfer_ratio", "转学分" in skill and "占比" in skill),
        ("d1_no_code_on_cert", "不展示" in skill and "代码" in skill),
        ("d2_literal_translate", "直接中文翻译" in skill or "国外专业直译" in skill),
        ("d3_cross_faculty", "跨学科门类" in skill or "跨门类" in skill),
        ("d4_ug_2026", "2026" in skill or "教高函〔2026〕" in (ROOT.parent / "reference.md").read_text(encoding="utf-8")),
        ("e3_qs_link_only", "预存" in skill and "QS" in skill),
        ("f1_double_first_class", "双一流" in skill and "985" in skill),
        ("f2_default_two", "默认 2 所" in skill or "默认**2**所" in skill),
        ("g_no_grade_in_final", "不得出现" in skill and "强" in skill),
        ("g2_nm", "只含强+中" in skill or "强或中" in skill),
        ("h3_risk_summary", "风险摘要" in skill),
        ("h1_system_first", "以系统提示为准" in skill),
        ("i2_banned_table", "生成禁用词" in (ROOT.parent / "templates.md").read_text(encoding="utf-8")),
        ("j1_script_degree", "degree_level" in (ROOT / "build_review_docx.py").read_text(encoding="utf-8")),
        ("j3_whitelist_note", "仅用于测试" in (Path(__file__).parent / "README.md").read_text(encoding="utf-8")
         or "仅测用" in (ROOT.parent / "reference.md").read_text(encoding="utf-8")),
        ("j4_maintain", "维护约定" in (ROOT.parent / "reference.md").read_text(encoding="utf-8")),
    ]

    files = sorted(FIX.glob("*.yaml"))
    if not files:
        print("No fixtures found", file=sys.stderr)
        return 2

    passed = failed = 0
    rows = []
    for name, ok in static_checks:
        if ok:
            passed += 1
            rows.append(("PASS", f"static_{name}", "pass", "OK"))
        else:
            failed += 1
            rows.append(("FAIL", f"static_{name}", "pass", "skill text missing expected gate"))
        if args.v or not ok:
            print(f"[{'PASS' if ok else 'FAIL'}] static_{name}")

    for fp in files:
        case = yaml.safe_load(fp.read_text(encoding="utf-8"))
        cid = case.get("case_id") or fp.stem
        expect = (case.get("expect") or "pass").lower()
        errs = validate_case(case) + run_check_consistency(case)
        ok = len(errs) == 0
        # expectation
        if expect == "pass":
            success = ok
            detail = "OK" if ok else "; ".join(errs)
        else:
            success = not ok  # must fail
            if success:
                detail = "caught: " + "; ".join(errs)
            else:
                detail = "EXPECTED_FAIL but passed gates"
        if success:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
        rows.append((status, cid, expect, detail))
        if args.v or not success:
            print(f"[{status}] {cid} (expect={expect})")
            print(f"  {detail}")

    print()
    print(f"Summary: {passed} passed, {failed} failed, {len(files)} total")
    for status, cid, expect, detail in rows:
        short = detail if len(detail) < 100 else detail[:97] + "..."
        print(f"  {status:4}  {cid:28}  expect={expect:4}  {short}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
