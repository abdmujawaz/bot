"""
db.py
كل التعامل مع قاعدة بيانات SQLite: إنشاء الجداول، تعبئة البيانات المرجعية
الثابتة (الكلية / الترمات / المواد / التصنيفات)، ودوال الإدخال الفعلية
لكل من Sheet / Question / Answer / Tag / QuestionTag / SubjectTag / TagStatistic.

الفكرة الأساسية لتوليد الـ uuid:
    كل جدول عنده id رقمي (AUTOINCREMENT) من SQLite أصلاً، فبنستخدم نفس
    الرقم كـ uuid (نص) لـ Sheet / Question / Answer / QuestionTag.
    هيك ما في داعي نحسب MAX(id)+1 يدوياً ولا نخزن حالة بين الجلسات:
    SQLite نفسه بيضمن انو ما في تكرار وانو الرقم دايماً تصاعدي.
"""

import sqlite3
import os

import tagging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
DB_PATH = os.path.join(BASE_DIR, "database.db")

# ---------------------------------------------------------------------------
# البيانات المرجعية الثابتة
# ---------------------------------------------------------------------------

COLLAGE_UUID = "COLLAGE-001"
COLLAGE_NAME = "كلية الطب البشري"

# (uuid, name, year, term, termType)
TERMS = [
    ("TERM-001", "الفصل الأول", None, "1", None),
    ("TERM-002", "الفصل الثاني", None, "2", None),
]

# (uuid, name, term_uuid)  -- المواد الدراسية، كل مادة مربوطة بترم معين
# ملاحظة: كلهن مفترَضين تابعين للفصل الأول (TERM-001) بناءً على اسم قاعدة
# البيانات الأصلية "Year3Term1" - إذا في مادة تابعة لترم مختلف قلي أعدلها.
SUBJECTS = [
    ("SUBJ-001", "الخمجية", "TERM-001"),
    ("SUBJ-002", "الهضمية", "TERM-001"),
    ("SUBJ-003", "القلبية", "TERM-001"),
    ("SUBJ-004", "الصدرية", "TERM-001"),
    ("SUBJ-005", "الكلية", "TERM-001"),
    ("SUBJ-006", "الدموية", "TERM-001"),
    ("SUBJ-007", "الغدية", "TERM-001"),
    ("SUBJ-008", "العصبية", "TERM-001"),
    ("SUBJ-009", "الطب النفسي", "TERM-001"),
    ("SUBJ-010", "اطفال 1", "TERM-001"),
    ("SUBJ-011", "اطفال 2", "TERM-001"),
    ("SUBJ-012", "جلدية", "TERM-001"),
]

# التصنيفات: 33 تصنيف مرضي (من ملف الخمجية) + 6 تصنيفات عريضة (الأقسام)
DISEASE_TAGS = [
    ("TAG-001", "الحمى التيفية"),
    ("TAG-002", "الحمى مجهولة السبب"),
    ("TAG-003", "أخماج المكورات العقدية"),
    ("TAG-004", "داء البروسيلا (الحمى المالطية)"),
    ("TAG-005", "الالتهاب الحاد"),
    ("TAG-006", "الليجونيلا"),
    ("TAG-007", "أخماج المشافي"),
    ("TAG-008", "التسمم الغذائي"),
    ("TAG-009", "انفلونزا النزلة الوافدة"),
    ("TAG-010", "الاسهالات"),
    ("TAG-011", "التمنيع"),
    ("TAG-012", "الإيدز (HIV)"),
    ("TAG-013", "داء المبيضات"),
    ("TAG-014", "الكوليرا"),
    ("TAG-015", "النكاف"),
    ("TAG-016", "Parvovirus B19"),
    ("TAG-017", "الكزاز"),
    ("TAG-018", "داء وحيدات النوى"),
    ("TAG-019", "التهاب الكبد C"),
    ("TAG-020", "اليرسينيا"),
    ("TAG-021", "العنقوديات"),
    ("TAG-022", "الحماق"),
    ("TAG-023", "CMV"),
    ("TAG-024", "الزحار العصوي"),
    ("TAG-025", "داء المقوسات"),
    ("TAG-026", "الصدمة الانتانية"),
    ("TAG-027", "الكلب"),
    ("TAG-028", "الحصبة"),
    ("TAG-029", "الكامبيلوباكتر"),
    ("TAG-030", "داء البلهارسيا"),
    ("TAG-031", "داء المستخفيات"),
    ("TAG-032", "الليشمانيا الحشوية"),
    ("TAG-033", "الحلأ البسيط"),
]

BROAD_TAGS = [
    ("TAG-034", "الأخماج الجرثومية"),
    ("TAG-035", "الأخماج الفيروسية"),
    ("TAG-036", "أخماج الأوالي والفطريات"),
    ("TAG-037", "التظاهرات السريرية"),
    ("TAG-038", "التهابات الكبد"),
    ("TAG-039", "منوعات"),
]

# خرائط تطبيع لبادئات الأقسام العريضة كما تظهر فعلياً بالملفات (مرادفات)
BROAD_PREFIX_ALIASES = {
    "الأخماج الجرثومية": "الأخماج الجرثومية",
    "قسم الجراثيم": "الأخماج الجرثومية",
    "الأخماج الفيروسية": "الأخماج الفيروسية",
    "قسم الفيروسات": "الأخماج الفيروسية",
    "أخماج الأوالي والفطريات": "أخماج الأوالي والفطريات",
    "التظاهرات السريرية": "التظاهرات السريرية",
    "التهابات الكبد": "التهابات الكبد",
    "منوعات": "منوعات",
}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_add_question_subject_uuid(conn):
    """للقواعد الموجودة من قبل (قبل إضافة هالعمود) - يضيفه تلقائياً بدون ما يفقد أي بيانات."""
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(Question)").fetchall()]
    if "subject_uuid" not in cols:
        conn.execute("ALTER TABLE Question ADD COLUMN subject_uuid TEXT")


def init_db():
    """ينشئ الجداول إذا مش موجودة، ويعبي البيانات المرجعية الثابتة (idempotent)."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    _migrate_add_question_subject_uuid(conn)

    conn.execute(
        "INSERT OR IGNORE INTO Collage (uuid, name) VALUES (?, ?)",
        (COLLAGE_UUID, COLLAGE_NAME),
    )
    for uuid_, name, year, term, term_type in TERMS:
        conn.execute(
            "INSERT OR IGNORE INTO Term (uuid, name, year, term, termType, collage_uuid) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uuid_, name, year, term, term_type, COLLAGE_UUID),
        )
    for uuid_, name, term_uuid in SUBJECTS:
        conn.execute(
            "INSERT OR IGNORE INTO Subject (uuid, name, term_uuid) VALUES (?, ?, ?)",
            (uuid_, name, term_uuid),
        )
    for uuid_, name in DISEASE_TAGS + BROAD_TAGS:
        conn.execute(
            "INSERT OR IGNORE INTO Tag (uuid, name) VALUES (?, ?)", (uuid_, name)
        )
    conn.commit()
    conn.close()


def get_all_subjects():
    conn = get_connection()
    rows = conn.execute("SELECT uuid, name FROM Subject ORDER BY name").fetchall()
    conn.close()
    return [(r["uuid"], r["name"]) for r in rows]


def get_all_tags():
    conn = get_connection()
    rows = conn.execute("SELECT uuid, name FROM Tag").fetchall()
    conn.close()
    return [(r["uuid"], r["name"]) for r in rows]


def create_new_tag(name):
    """ينشئ Tag جديد بـ uuid تصاعدي بصيغة TAG-0XX ويرجع الـ uuid."""
    conn = get_connection()
    row = conn.execute("SELECT uuid FROM Tag ORDER BY id DESC LIMIT 1").fetchone()
    last_num = int(row["uuid"].split("-")[1]) if row else 0
    new_uuid = f"TAG-{last_num + 1:03d}"
    conn.execute("INSERT INTO Tag (uuid, name) VALUES (?, ?)", (new_uuid, name))
    conn.commit()
    conn.close()
    return new_uuid


def find_matching_sheet(year, term_text, similarity_threshold=0.80):
    """
    يدور على شيت موجود بنفس السنة وباسم دورة مشابه (مش لازم متطابق حرفياً -
    'تشرين أساسية' لازم تلاقي 'تشرين الأساسية' مثلاً). بيرجع uuid الشيت
    الأقرب تشابهاً إذا لقى، وإلا None.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT uuid, term FROM Sheet WHERE year = ?", (year,)
    ).fetchall()
    conn.close()

    best_uuid, best_score = None, 0.0
    for r in rows:
        score = tagging.similarity(term_text, r["term"])
        if score >= similarity_threshold and score > best_score:
            best_uuid, best_score = r["uuid"], score
    return best_uuid


def get_or_create_sheet(conn, subject_uuid, year, term_text):
    """
    بيرجع uuid شيت موجود إذا لقى تطابق (سنة + دورة مشابهة)، وإلا بينشئ شيت
    جديد. subject_uuid هون بيتسجل بس لأول مادة بتنشئ الشيت (معلومة تقريبية
    غير حاسمة)، لأنو الحقيقة الدقيقة لمادة كل سؤال محفوظة بعمود
    Question.subject_uuid مش هون.
    """
    existing_uuid = find_matching_sheet(year, term_text)
    if existing_uuid:
        return existing_uuid, False

    cur = conn.execute(
        "INSERT INTO Sheet (uuid, text, languageDirection, term, year, term_uuid, "
        "notes, type, questionsCount, subject_uuid, examDate) "
        "VALUES ('', '', ?, ?, ?, NULL, NULL, ?, 0, ?, NULL)",
        (1, term_text, year, 0, subject_uuid),
    )
    sheet_id = cur.lastrowid
    sheet_uuid = str(sheet_id)
    conn.execute("UPDATE Sheet SET uuid = ? WHERE id = ?", (sheet_uuid, sheet_id))
    return sheet_uuid, True


def insert_question(conn, sheet_uuid, subject_uuid, text, note, display_order):
    cur = conn.execute(
        "INSERT INTO Question (uuid, text, display_order, sheet_uuid, note, "
        "answersCleanText, questionType, subject_uuid) VALUES ('', ?, ?, ?, ?, '', 0, ?)",
        (text, display_order, sheet_uuid, note, subject_uuid),
    )
    q_id = cur.lastrowid
    q_uuid = str(q_id)
    conn.execute("UPDATE Question SET uuid = ? WHERE id = ?", (q_uuid, q_id))
    return q_uuid


def insert_answer(conn, question_uuid, text, label, is_correct):
    cur = conn.execute(
        "INSERT INTO Answer (uuid, text, answerLabel, question_uuid, isCorrect) "
        "VALUES ('', ?, ?, ?, ?)",
        (text, label, question_uuid, 1 if is_correct else 0),
    )
    a_id = cur.lastrowid
    a_uuid = str(a_id)
    conn.execute("UPDATE Answer SET uuid = ? WHERE id = ?", (a_uuid, a_id))
    return a_uuid


def link_question_tag(conn, question_uuid, tag_uuid):
    cur = conn.execute(
        "INSERT OR IGNORE INTO QuestionTag (uuid, question_uuid, tag_uuid) "
        "VALUES ('', ?, ?)",
        (question_uuid, tag_uuid),
    )
    if cur.lastrowid and cur.rowcount:
        qt_id = cur.lastrowid
        conn.execute(
            "UPDATE QuestionTag SET uuid = ? WHERE id = ?", (str(qt_id), qt_id)
        )


def link_subject_tag(conn, subject_uuid, tag_uuid):
    conn.execute(
        "INSERT OR IGNORE INTO SubjectTag (subject_uuid, tag_uuid) VALUES (?, ?)",
        (subject_uuid, tag_uuid),
    )


def bump_tag_statistic(conn, tag_uuid, subject_uuid):
    row = conn.execute(
        "SELECT id, count FROM TagStatistic WHERE tag_uuid = ? AND subject_uuid = ?",
        (tag_uuid, subject_uuid),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE TagStatistic SET count = ? WHERE id = ?",
            (row["count"] + 1, row["id"]),
        )
    else:
        cur = conn.execute(
            "INSERT INTO TagStatistic (uuid, banksCount, examsCount, count, "
            "category, name, tag_uuid, subject_uuid) VALUES ('', 0, 0, 1, NULL, NULL, ?, ?)",
            (tag_uuid, subject_uuid),
        )
        ts_id = cur.lastrowid
        conn.execute(
            "UPDATE TagStatistic SET uuid = ? WHERE id = ?", (str(ts_id), ts_id)
        )


def get_max_display_order(conn, sheet_uuid):
    row = conn.execute(
        "SELECT MAX(display_order) m FROM Question WHERE sheet_uuid = ?", (sheet_uuid,)
    ).fetchone()
    return row["m"] or 0


def finalize_sheet_count(conn, sheet_uuid):
    """بيحسب العدد الحقيقي من قاعدة البيانات (مجموع كل المواد المشتركة
    بنفس الشيت)، مش بس دفعة الاستيراد الحالية."""
    count = conn.execute(
        "SELECT COUNT(*) c FROM Question WHERE sheet_uuid = ?", (sheet_uuid,)
    ).fetchone()["c"]
    conn.execute("UPDATE Sheet SET questionsCount = ? WHERE uuid = ?", (count, sheet_uuid))


# ---------------------------------------------------------------------------
# دوال البحث / التصفح / التعديل (لواجهة التحكم)
# ---------------------------------------------------------------------------

def search_questions_by_text(keyword, limit=8, offset=0):
    conn = get_connection()
    rows = conn.execute(
        "SELECT uuid, text FROM Question WHERE text LIKE ? ORDER BY id "
        "LIMIT ? OFFSET ?",
        (f"%{keyword}%", limit, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) c FROM Question WHERE text LIKE ?", (f"%{keyword}%",)
    ).fetchone()["c"]
    conn.close()
    return [(r["uuid"], r["text"]) for r in rows], total


def get_question_by_uuid(question_uuid):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM Question WHERE uuid = ?", (question_uuid,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_sheets_by_subject(subject_uuid, limit=10, offset=0):
    """بيرجع الشيتات يلي فيها على الأقل سؤال وحدة لهاي المادة - معتمد على
    Question.subject_uuid مش Sheet.subject_uuid (لأنو الشيت مشتركة بين
    عدة مواد، وSheet.subject_uuid بس بيعكس أول مادة أنشأتها)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT Sheet.uuid, Sheet.year, Sheet.term, "
        "  (SELECT COUNT(*) FROM Question q2 WHERE q2.sheet_uuid = Sheet.uuid "
        "     AND q2.subject_uuid = ?) AS subj_count "
        "FROM Sheet WHERE EXISTS ("
        "  SELECT 1 FROM Question q3 WHERE q3.sheet_uuid = Sheet.uuid AND q3.subject_uuid = ?"
        ") ORDER BY Sheet.year DESC, Sheet.id LIMIT ? OFFSET ?",
        (subject_uuid, subject_uuid, limit, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) c FROM Sheet WHERE EXISTS ("
        "  SELECT 1 FROM Question q3 WHERE q3.sheet_uuid = Sheet.uuid AND q3.subject_uuid = ?"
        ")",
        (subject_uuid,),
    ).fetchone()["c"]
    conn.close()
    return [(r["uuid"], r["year"], r["term"], r["subj_count"]) for r in rows], total


def get_questions_by_sheet(sheet_uuid, subject_uuid=None, limit=8, offset=0):
    """لو انعطى subject_uuid، بيرجع بس أسئلة هاي المادة من هاي الشيت
    (لأنو الشيت هلق مشتركة بين كل المواد يلي عندها نفس التاريخ)."""
    conn = get_connection()
    if subject_uuid:
        rows = conn.execute(
            "SELECT uuid, text, display_order FROM Question "
            "WHERE sheet_uuid = ? AND subject_uuid = ? "
            "ORDER BY display_order LIMIT ? OFFSET ?",
            (sheet_uuid, subject_uuid, limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) c FROM Question WHERE sheet_uuid = ? AND subject_uuid = ?",
            (sheet_uuid, subject_uuid),
        ).fetchone()["c"]
    else:
        rows = conn.execute(
            "SELECT uuid, text, display_order FROM Question WHERE sheet_uuid = ? "
            "ORDER BY display_order LIMIT ? OFFSET ?",
            (sheet_uuid, limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) c FROM Question WHERE sheet_uuid = ?", (sheet_uuid,)
        ).fetchone()["c"]
    conn.close()
    return [(r["uuid"], r["text"], r["display_order"]) for r in rows], total


def get_answers_for_question(question_uuid):
    conn = get_connection()
    rows = conn.execute(
        "SELECT uuid, text, answerLabel, isCorrect FROM Answer WHERE question_uuid = ? "
        "ORDER BY answerLabel",
        (question_uuid,),
    ).fetchall()
    conn.close()
    return [(r["uuid"], r["text"], r["answerLabel"], r["isCorrect"]) for r in rows]


def get_tags_for_question(question_uuid):
    conn = get_connection()
    rows = conn.execute(
        "SELECT Tag.uuid, Tag.name FROM Tag "
        "JOIN QuestionTag ON QuestionTag.tag_uuid = Tag.uuid "
        "WHERE QuestionTag.question_uuid = ?",
        (question_uuid,),
    ).fetchall()
    conn.close()
    return [(r["uuid"], r["name"]) for r in rows]


def update_question_text(question_uuid, new_text):
    conn = get_connection()
    conn.execute("UPDATE Question SET text = ? WHERE uuid = ?", (new_text, question_uuid))
    conn.commit()
    conn.close()


def update_note(question_uuid, new_note):
    conn = get_connection()
    conn.execute("UPDATE Question SET note = ? WHERE uuid = ?", (new_note, question_uuid))
    conn.commit()
    conn.close()


def update_answer_text(answer_uuid, new_text):
    conn = get_connection()
    conn.execute("UPDATE Answer SET text = ? WHERE uuid = ?", (new_text, answer_uuid))
    conn.commit()
    conn.close()


def set_correct_answer(question_uuid, answer_uuid):
    """بيصحح isCorrect لكل خيارات السؤال: 1 للمختار، 0 للباقي - أوتوماتيك."""
    conn = get_connection()
    conn.execute(
        "UPDATE Answer SET isCorrect = 0 WHERE question_uuid = ?", (question_uuid,)
    )
    conn.execute(
        "UPDATE Answer SET isCorrect = 1 WHERE uuid = ?", (answer_uuid,)
    )
    conn.commit()
    conn.close()


def remove_question_tag(question_uuid, tag_uuid):
    """بيشيل الربط، وبينقص عداد TagStatistic أوتوماتيك (بدون ما ينزل تحت صفر)."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM QuestionTag WHERE question_uuid = ? AND tag_uuid = ?",
        (question_uuid, tag_uuid),
    )
    row = conn.execute(
        "SELECT subject_uuid FROM Question WHERE uuid = ?", (question_uuid,)
    ).fetchone()
    if row and row["subject_uuid"]:
        subject_uuid = row["subject_uuid"]
        stat = conn.execute(
            "SELECT id, count FROM TagStatistic WHERE tag_uuid = ? AND subject_uuid = ?",
            (tag_uuid, subject_uuid),
        ).fetchone()
        if stat and stat["count"] > 0:
            conn.execute(
                "UPDATE TagStatistic SET count = ? WHERE id = ?",
                (stat["count"] - 1, stat["id"]),
            )
    conn.commit()
    conn.close()


def add_question_tag_full(question_uuid, tag_uuid):
    """بيربط تصنيف جديد بسؤال، وبيحدث SubjectTag و TagStatistic أوتوماتيك."""
    conn = get_connection()
    row = conn.execute(
        "SELECT subject_uuid FROM Question WHERE uuid = ?", (question_uuid,)
    ).fetchone()
    link_question_tag(conn, question_uuid, tag_uuid)
    if row and row["subject_uuid"]:
        subject_uuid = row["subject_uuid"]
        link_subject_tag(conn, subject_uuid, tag_uuid)
        bump_tag_statistic(conn, tag_uuid, subject_uuid)
    conn.commit()
    conn.close()
