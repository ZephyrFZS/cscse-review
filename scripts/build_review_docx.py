#!/usr/bin/env python3
"""Build CSCSE review supporting Word doc from case.yaml + courses.json.

Requires: pip install python-docx pyyaml

Usage:
  python build_review_docx.py case.yaml -o 个人陈述申请及相关证明材料.docx

Notes:
  - case.yaml MUST include degree_level: 本科/学士 | 硕士 | 博士
  - Prose must already follow templates.md (banned words, N/M口径, 申请句).
  - This script layouts structure; always proofread against templates before submit.
  - Do NOT put 强/中/弱 labels into domestic mapping cells.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

GRADE_LEAK = re.compile(r"(强对应|中对应|弱对应|高度一致|完全等同|保证通过|QS\s*前|证书将显示代码)")


def normalize_level(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("本科") or s == "学士":
        return "本科"
    if s.startswith("硕士"):
        return "硕士"
    if s.startswith("博士"):
        return "博士"
    return s


def clean_cell(v) -> str:
    s = str(v if v is not None else "—")
    # never print internal grades
    for bad in ("（强）", "(强)", "（中）", "(中)", "（弱）", "(弱)", "强：", "中：", "弱："):
        s = s.replace(bad, "")
    return s.strip() or "—"


def set_font(run, size=None, bold=None, east="宋体"):
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold


def shade(cell, color="D9E2F3"):
    tc_pr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


class Builder:
    def __init__(self, case: dict, courses: dict):
        self.case = case
        self.courses = courses
        self.doc = Document()
        st = self.doc.styles["Normal"]
        st.font.name = "Times New Roman"
        st.font.size = Pt(11)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        for s in self.doc.sections:
            s.left_margin = s.right_margin = Cm(2.2)
            s.top_margin = s.bottom_margin = Cm(2.0)

    def H(self, text, level=1):
        p = self.doc.add_paragraph()
        r = p.add_run(text)
        set_font(r, {0: 18, 1: 14, 2: 12}[level], True, "黑体")
        if level == 0:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(6)

    def P(self, text, indent=True, size=11, bold=False, align=None):
        p = self.doc.add_paragraph()
        r = p.add_run(text)
        set_font(r, size, bold)
        if indent:
            p.paragraph_format.first_line_indent = Pt(size * 2)
        p.paragraph_format.line_spacing = 1.4
        if align:
            p.alignment = align

    def table(self, headers, rows, widths=None, size=9):
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(headers):
            c = t.rows[0].cells[i]
            c.text = ""
            set_font(c.paragraphs[0].add_run(h), size, True, "黑体")
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            shade(c)
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                set_font(cells[i].paragraphs[0].add_run(str(v)), size)
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        self.doc.add_paragraph()

    def build(self) -> Document:
        c = self.case
        a = c["applicant"]
        r = c.get("request") or {}
        f = c.get("foreign") or {}
        domestic = c.get("domestic") or []
        mappings = c.get("mappings") or []
        modules = c.get("modules") or []
        level = normalize_level(c.get("degree_level", ""))

        self.H("国外学历学位认证复核申请", 0)
        self.H("个人陈述申请及相关证明材料", 0)

        target = r.get("target_major") or ""
        field = r.get("discipline") or ""
        # 对外强调专业领域中文名；代码仅内部核对，不写成「证书打印代码」
        apply_line = f"申请专业领域/名称：{target or field}"
        if field and target and field not in target:
            apply_line = f"申请专业领域：{field}；专业名称：{target}"

        info = self.doc.add_table(rows=0, cols=2)
        info.style = "Table Grid"
        for k, v in [
            ("申请人", f"{a.get('name_zh','')}（{a.get('name_en','')}）"),
            ("学历层次", level or c.get("degree_level", "")),
            ("原认证书编号", a.get("cert_no", "")),
            ("就读院校", f.get("school_zh", "") or f.get("school_en", "")),
            ("就读项目", f"{f.get('program','')}（{f.get('program_code','')}）".replace("（）", "")),
            ("开设学院", f.get("school_unit", "")),
            ("原认证结果", a.get("original_major", "")),
            ("申请复核为", apply_line),
        ]:
            cells = info.add_row().cells
            cells[0].text = ""
            cells[1].text = ""
            set_font(cells[0].paragraphs[0].add_run(k), 10.5, True)
            set_font(cells[1].paragraphs[0].add_run(v), 10.5)
            shade(cells[0], "F2F2F2")
            cells[0].width = Cm(3)
            cells[1].width = Cm(13.5)

        self.doc.add_paragraph()
        self.H("目　录", 0)
        toc = [
            ("一、个人陈述", 0),
            ("二、培养目标与研究方向对比", 0),
        ]
        if level == "博士":
            toc += [("三、培养环节对照", 0), ("四、课程对比（辅）", 0), ("五、附录", 0)]
            course_heading = "四、课程对比（辅）"
            module_heading = "三、培养环节对照"
            appendix_heading = "五、附录"
        else:
            toc += [("三、课程对比", 0), ("四、附录", 0)]
            course_heading = "三、课程对比"
            module_heading = None
            appendix_heading = "四、附录"
        toc += [
            (f"附录一：培养方案及课程信息来源", 1),
            (f"附录二：国外课程描述原文", 1),
            (f"附录三：提交附件清单", 1),
        ]
        for text, lvl in toc:
            p = self.doc.add_paragraph()
            set_font(p.add_run(text), 12 if lvl == 0 else 11, lvl == 0)
            p.paragraph_format.left_indent = Cm(1.0 + lvl * 1.0)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.5
        self.doc.add_page_break()

        # 个人陈述
        self.H("一、个人陈述")
        stmt = c.get("personal_statement")
        if stmt:
            for para in stmt.strip().split("\n"):
                if para.strip():
                    self.P(
                        para.strip(),
                        indent=not para.strip().startswith(
                            ("1.", "2.", "3.", "此致", "申请人", "恳请", "尊敬", "您好")
                        ),
                    )
        else:
            self.P("（请在 case.yaml 的 personal_statement 字段按 templates.md 填写）", indent=False)
        self.P("申请人（签名）：＿＿＿＿＿＿＿＿（线上提交以系统为准，非强制手签）", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
        self.P(a.get("sign_date", ""), indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
        self.doc.add_page_break()

        # 培养目标
        self.H("二、培养目标与研究方向对比")
        goal_rows = c.get("goal_comparison") or []
        if goal_rows:
            headers = ["对比项", f.get("program", "国外项目")] + [d.get("name", "") for d in domestic]
            self.table(headers, [[clean_cell(x) for x in row] for row in goal_rows], size=9)
        else:
            self.P("（在 case.yaml 的 goal_comparison 中填写对比行）", indent=False)

        # 博士环节主表
        if level == "博士":
            self.H(module_heading)
            if modules:
                dnames = [d.get("name", f"高校{i+1}") for i, d in enumerate(domestic)]
                headers = ["序号", "国外环节/要求", "依据来源", "主要内容"] + dnames
                rows = []
                for i, m in enumerate(modules, 1):
                    row = [
                        i,
                        clean_cell(m.get("name", "")),
                        clean_cell(m.get("source", "")),
                        clean_cell(m.get("desc", "")),
                    ]
                    for j, _ in enumerate(domestic):
                        row.append(clean_cell(m.get(f"domestic_{j}", "—")))
                    rows.append(row)
                self.table(headers, rows, size=8.5)
            else:
                self.P("（博士课少时请在 case.yaml 的 modules 填写培养环节对照）", indent=False)

        # 课程对比 — landscape
        new = self.doc.add_section()
        new.orientation = WD_ORIENT.LANDSCAPE
        new.page_width, new.page_height = new.page_height, new.page_width
        new.left_margin = new.right_margin = Cm(1.8)
        self.H(course_heading)
        if level == "博士":
            self.P("以下为授课课程对照（辅）；研究型项目以培养环节为主。", indent=False, size=9)
        note = c.get("course_table_note", "")
        if note:
            self.P(note, indent=False, size=9)
        dnames = [d.get("name", f"高校{i+1}") for i, d in enumerate(domestic)]
        headers = ["序号", "课号", "课程名称", "修读方式", "主要内容"] + dnames
        rows = []
        for i, m in enumerate(mappings, 1):
            code = m.get("code", "")
            title = m.get("title") or (
                f"{self.courses.get(code, {}).get('title', '')}" if code in self.courses else ""
            )
            if m.get("title_zh"):
                title = f"{m['title_zh']}\n{title}" if title else m["title_zh"]
            desc = m.get("desc") or self.courses.get(code, {}).get("desc", "")
            row = [
                i,
                code,
                clean_cell(title),
                clean_cell(m.get("mode", "")),
                clean_cell(desc[:200] + ("…" if len(desc) > 200 else "")),
            ]
            for j, _ in enumerate(domestic):
                key = f"domestic_{j}"
                if key in m:
                    cell = m.get(key)
                elif isinstance(m.get("domestic"), list) and j < len(m["domestic"]):
                    cell = m["domestic"][j]
                else:
                    cell = "—"
                # 弱/无 → 终稿 —
                if (m.get("strength") or "") in {"弱", "无"}:
                    cell = "—"
                row.append(clean_cell(cell))
            rows.append(row)
        self.table(headers, rows, size=8.5)
        credit_note = c.get("credit_note", "")
        if credit_note:
            self.P(credit_note, indent=False, size=9.5)

        # 附录 — portrait
        back = self.doc.add_section()
        back.orientation = WD_ORIENT.PORTRAIT
        back.page_width, back.page_height = back.page_height, back.page_width
        back.left_margin = back.right_margin = Cm(2.2)
        self.H(appendix_heading)
        self.H("附录一：培养方案及课程信息来源", 2)
        if f.get("handbook_program_url"):
            self.P(f"国外项目页：{f['handbook_program_url']}", indent=False, size=10)
        for d in domestic:
            year = d.get("plan_year") or d.get("version", "")
            self.P(f"{d.get('name','')}：{d.get('url','')}（{year}）", indent=False, size=10)
        for code in [m.get("code") for m in mappings if m.get("code")]:
            meta = self.courses.get(code) or {}
            if meta.get("url"):
                yr = meta.get("year", "")
                self.P(f"{code} {meta.get('title','')}：{meta['url']}" + (f"（{yr}）" if yr else ""), indent=False, size=10)

        self.H("附录二：国外课程描述原文", 2)
        for code in [m.get("code") for m in mappings if m.get("code")]:
            meta = self.courses.get(code) or {}
            if not meta:
                continue
            self.P(
                f"{code} {meta.get('title','')}（{meta.get('uoc','')}，{meta.get('year','')}）",
                indent=False,
                size=10,
                bold=True,
            )
            self.P(meta.get("desc", ""), indent=False, size=9)

        self.H("附录三：提交附件清单", 2)
        for item in c.get("attachments") or []:
            self.P(item, indent=False, size=10)

        return self.doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_yaml")
    ap.add_argument("-o", "--output", default="个人陈述申请及相关证明材料.docx")
    ap.add_argument("--courses", default="courses.json")
    args = ap.parse_args()
    case = yaml.safe_load(Path(args.case_yaml).read_text(encoding="utf-8"))
    level = normalize_level(case.get("degree_level", ""))
    if not level:
        print("ERROR: case.yaml 缺少 degree_level（本科/学士|硕士|博士）", file=sys.stderr)
        sys.exit(2)
    for label in ("personal_statement", "review_reason"):
        text = case.get(label) or ""
        if GRADE_LEAK.search(text):
            print(f"ERROR: {label} 含禁用表述，请按 templates.md 修改后再生成", file=sys.stderr)
            sys.exit(1)
    courses_path = Path(args.courses)
    courses = json.loads(courses_path.read_text(encoding="utf-8")) if courses_path.exists() else {}
    if isinstance(courses, list):
        courses = {x["code"]: x for x in courses if "code" in x}
    doc = Builder(case, courses).build()
    doc.save(args.output)
    print("wrote", args.output, f"(degree_level={level})")


if __name__ == "__main__":
    main()
