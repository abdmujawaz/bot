"""
parser.py
يحوّل نص ملف الـ txt (بالقالب المعتمد) إلى بنية بيانات بايثون بسيطة:

[
  {
    "year": 2025,
    "term_text": "تموز - الأساسية",
    "questions": [
      {
        "text": "...",
        "options": {"A": "...", "B": "...", ...},
        "correct_letter": "D",
        "explanation": "...",
        "attention": "...",
        "broad_tag_raw": "الأخماج الجرثومية" | None,
        "specific_tag_raw": "الحمى التيفية",
      },
      ...
    ],
  },
  ...
]

هاد الملف ما بيلمس قاعدة البيانات إطلاقاً - شغلو بس تحويل نص لبنية بيانات.
"""

import re

HEADER_RE_DASH = re.compile(r"^##\s*(?P<year>[\d/]+)\s*-\s*(?P<session>.+?)\s*$")
HEADER_RE_PAREN = re.compile(r"^##\s*(?P<year>[\d/]+)\s*\(\s*(?P<session>.+?)\s*\)\s*$")
TAG_RE = re.compile(r"^\*\*(?!الإجابة الصحيحة|شرح[:：]|انتبه[:：])(?P<tag>.+?)\*\*$")
QUESTION_RE = re.compile(r"^السؤال\s*\d+\s*[:：]\s*(?P<text>.+)$")
OPTION_RE = re.compile(r"^(?P<letter>[A-Ea-e])[\.\)]\s*(?P<text>.+)$")
CORRECT_RE = re.compile(r"^\*\*الإجابة الصحيحة\s*[:：]\s*(?P<letter>[A-Ea-e])\*\*$")
EXPLAIN_RE = re.compile(r"^\*\*شرح[:：]\*\*\s*(?P<text>.+)$")
ATTENTION_RE = re.compile(r"^\*\*انتبه[:：]\*\*\s*(?P<text>.+)$")


def _split_tag(raw_tag):
    """يقسم عنوان التصنيف إلى (broad_raw أو None, specific_raw) حسب وجود شرطة فاصلة."""
    for dash in ("–", "—", "-"):
        if dash in raw_tag:
            parts = raw_tag.split(dash, 1)
            broad = parts[0].strip()
            specific = parts[1].strip()
            if broad and specific:
                return broad, specific
    return None, raw_tag.strip()


def _parse_year(raw_year):
    """يدعم صيغة 'YYYY' أو 'YYYY/YYYY' (بياخد أول رقم بهاي الحالة)."""
    first = raw_year.split("/")[0].strip()
    try:
        return int(first)
    except ValueError:
        return None


def parse_file(content):
    lines = content.splitlines()

    sheets = []
    current_sheet = None
    current_broad_raw = None
    current_specific_raw = None
    pending_question = None

    def finalize_question():
        nonlocal pending_question
        if pending_question is not None and current_sheet is not None:
            # سؤال يعتبر صالح فقط إذا فيه نص وخيارات وجواب صحيح محدد
            if pending_question["text"] and pending_question["correct_letter"]:
                current_sheet["questions"].append(pending_question)
        pending_question = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        m = HEADER_RE_PAREN.match(line) or HEADER_RE_DASH.match(line)
        if m:
            finalize_question()
            current_sheet = {
                "year": _parse_year(m.group("year")),
                "term_text": m.group("session").strip(),
                "questions": [],
            }
            sheets.append(current_sheet)
            current_broad_raw, current_specific_raw = None, None
            continue

        m = TAG_RE.match(line)
        if m:
            finalize_question()
            current_broad_raw, current_specific_raw = _split_tag(m.group("tag"))
            continue

        m = QUESTION_RE.match(line)
        if m:
            finalize_question()
            pending_question = {
                "text": m.group("text").strip(),
                "options": {},
                "correct_letter": None,
                "explanation": None,
                "attention": None,
                "broad_tag_raw": current_broad_raw,
                "specific_tag_raw": current_specific_raw,
            }
            continue

        m = CORRECT_RE.match(line)
        if m and pending_question is not None:
            pending_question["correct_letter"] = m.group("letter").upper()
            continue

        m = EXPLAIN_RE.match(line)
        if m and pending_question is not None:
            pending_question["explanation"] = m.group("text").strip()
            continue

        m = ATTENTION_RE.match(line)
        if m and pending_question is not None:
            pending_question["attention"] = m.group("text").strip()
            continue

        m = OPTION_RE.match(line)
        if m and pending_question is not None:
            letter = m.group("letter").upper()
            pending_question["options"][letter] = m.group("text").strip()
            continue

        # أي سطر تاني (متل استمرار نص) بيتجاهل حالياً - القالب المعتمد كل حقل بسطر وحدة

    finalize_question()

    # تصفية الشيتات الفارغة (بلا أسئلة صالحة)
    sheets = [s for s in sheets if s["questions"]]
    return sheets


def build_note(explanation, attention):
    """يدمج الشرح + انتبه بحقل note واحد حسب القرار المعتمد."""
    parts = []
    if explanation:
        parts.append(explanation)
    if attention:
        parts.append(f"انتبه: {attention}")
    return "\n".join(parts) if parts else None


LETTER_TO_LABEL = {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"}
