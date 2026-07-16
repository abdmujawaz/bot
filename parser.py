"""
parser.py
يحوّل نص ملف الـ txt (بالقالب المعتمد) إلى بنية بيانات بايثون بسيطة.
"""

import re

HEADER_RE_DASH = re.compile(r"^##\s*(?P<year>[\d/]+)\s*-\s*(?P<session>.+?)\s*$")
HEADER_RE_PAREN = re.compile(r"^##\s*(?P<year>[\d/]+)\s*\(\s*(?P<session>.+?)\s*\)\s*$")
_HEADER_ANY_RE = re.compile(r"^##\s*(?P<rest>.+?)\s*$")
_YEAR_TOKEN_RE = re.compile(r"(?P<year>\d{4}(?:/\d{4})?)")
TAG_RE = re.compile(r"^\*\*(?!الإجابة الصحيحة|شرح[:：]|انتبه[:：])(?P<tag>.+?)\*\*$")
QUESTION_RE = re.compile(r"^السؤال\s*\d+\s*[:：]\s*(?P<text>.+)$")
OPTION_RE = re.compile(r"^(?P<letter>[A-Ea-e])[\.\)]\s*(?P<text>.+)$")
# ملاحظة: النجمتين ** اختياريتين هلق (\*{0,2}) - بعض الملفات بتكتب هاد
# السطر بدون تنسيق bold، وبعضها معه، والاثنين لازم ينقبلوا.
CORRECT_RE = re.compile(r"^\*{0,2}الإجابة الصحيحة\s*[:：]\s*(?P<letter>[A-Ea-e])\*{0,2}$")
EXPLAIN_RE = re.compile(r"^\*{0,2}شرح[:：]\*{0,2}\s*(?P<text>.+)$")
ATTENTION_RE = re.compile(r"^\*{0,2}انتبه[:：]\*{0,2}\s*(?P<text>.+)$")
# سطر فاصل زخرفي (----- أو =====) - بيستخدم كإشارة إنو السطر يلي بعده
# غالبًا عنوان تصنيف حتى لو مش محاط بـ **
SEPARATOR_RE = re.compile(r"^[-=]{3,}$")


def _split_tag(raw_tag):
    for dash in ("–", "—", "-"):
        if dash in raw_tag:
            parts = raw_tag.split(dash, 1)
            broad = parts[0].strip()
            specific = parts[1].strip()
            if broad and specific:
                return broad, specific
    return None, raw_tag.strip()


def _parse_year(raw_year):
    first = raw_year.split("/")[0].strip()
    try:
        return int(first)
    except ValueError:
        return None


def _parse_header_line(line):
    """يفهم عنوان الشيت (سطر ## ...) بمرونة: بيدور على رقم السنة بأي
    مكان بالسطر (مش لازم يكون أول شي فورًا بعد ##)، وبيبني term_text من
    باقي الكلام حوليها - هيك بتنقبل صيغ زي:
    '## 2025 - تموز (التكميلية)'
    و
    '## بنك الأسئلة القديم – أيلول 2022 (الأساسية)'
    بنفس الوقت، بدل ما تنرفض العناوين يلي فيها بادئة زخرفية قبل السنة."""
    m = _HEADER_ANY_RE.match(line)
    if not m:
        return None
    rest = m.group("rest")
    ym = _YEAR_TOKEN_RE.search(rest)
    if not ym:
        return None
    year = _parse_year(ym.group("year"))
    if year is None:
        return None

    before = rest[: ym.start()]
    after = rest[ym.end():]
    for dash in ("–", "—", "-"):
        if dash in before:
            before = before.split(dash)[-1]
    before = before.strip(" -–—")
    after = after.strip(" -–—")
    term_text = " ".join(p for p in (before, after) if p).strip()
    return year, term_text


def parse_file(content):
    lines = content.splitlines()

    sheets = []
    current_sheet = None
    current_broad_raw = None
    current_specific_raw = None
    pending_question = None
    prev_line = None

    def finalize_question():
        nonlocal pending_question
        if pending_question is not None and current_sheet is not None:
            if pending_question["text"] and pending_question["correct_letter"]:
                current_sheet["questions"].append(pending_question)
        pending_question = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("##"):
            parsed = _parse_header_line(line)
            if parsed:
                year, term_text = parsed
                finalize_question()
                current_sheet = {
                    "year": year,
                    "term_text": term_text,
                    "questions": [],
                }
                sheets.append(current_sheet)
                current_broad_raw, current_specific_raw = None, None
                prev_line = line
                continue

        m = TAG_RE.match(line)
        if m:
            finalize_question()
            current_broad_raw, current_specific_raw = _split_tag(m.group("tag"))
            prev_line = line
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
            prev_line = line
            continue

        m = CORRECT_RE.match(line)
        if m and pending_question is not None:
            pending_question["correct_letter"] = m.group("letter").upper()
            prev_line = line
            continue

        m = EXPLAIN_RE.match(line)
        if m and pending_question is not None:
            pending_question["explanation"] = m.group("text").strip()
            prev_line = line
            continue

        m = ATTENTION_RE.match(line)
        if m and pending_question is not None:
            pending_question["attention"] = m.group("text").strip()
            prev_line = line
            continue

        m = OPTION_RE.match(line)
        if m and pending_question is not None:
            letter = m.group("letter").upper()
            pending_question["options"][letter] = m.group("text").strip()
            prev_line = line
            continue

        # احتياطي: سطر تصنيف مكتوب بدون ** لكن جاي مباشرة بعد سطر فاصل
        # (----- أو =====) - نفس منطق التصنيف العادي، بس بدون شرط الـ bold
        if (
            prev_line is not None
            and SEPARATOR_RE.match(prev_line)
            and not line.startswith("##")
            and not any(
                rx.match(line)
                for rx in (QUESTION_RE, OPTION_RE, CORRECT_RE, EXPLAIN_RE, ATTENTION_RE)
            )
        ):
            finalize_question()
            current_broad_raw, current_specific_raw = _split_tag(line)
            prev_line = line
            continue

        # أي سطر تاني (متل استمرار نص) بيتجاهل حالياً - القالب المعتمد كل حقل بسطر وحدة
        prev_line = line

    finalize_question()

    sheets = [s for s in sheets if s["questions"]]
    return sheets


def build_note(explanation, attention):
    parts = []
    if explanation:
        parts.append(explanation)
    if attention:
        parts.append(f"انتبه: {attention}")
    return "\n".join(parts) if parts else None


LETTER_TO_LABEL = {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"}
