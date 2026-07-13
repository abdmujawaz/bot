"""
bot.py
بوت تليجرام يستقبل ملف txt (بالقالب المعتمد)، يخليك تختار المادة،
يحل أي تصنيف مشكوك فيه بالتفاعل معك عبر أزرار Yes/No، وبعدين يدخل
كل شي (Sheet/Question/Answer/Tag/QuestionTag) لقاعدة بيانات SQLite حقيقية
دائمة (database.db) بجانب هاد الملف.

تشغيل:
    pip install -r requirements.txt
    python bot.py
"""

import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import db
import parser as p
import tagging as t

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# سيرفر HTTP صغير (بس عشان Render يعتبر التطبيق "شغال" ويأهله للخطة المجانية)
# البوت نفسه بيشتغل بمنطق منفصل تماماً (Polling مع تليجرام) بخيط رئيسي
# ---------------------------------------------------------------------------

class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("البوت شغال ✅".encode("utf-8"))

    def log_message(self, format, *args):
        pass  # تجاهل تسجيل كل طلب health-check حتى ما يزعج اللوج


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    logger.info(f"سيرفر الـ health-check شغال على المنفذ {port}")
    server.serve_forever()


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def _safe_answer(query):
    """يتجاهل خطأ 'Query is too old' الناتج عن ضغطة مكررة/متأخرة على الزر
    بدل ما يوقف البوت كامل."""
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"تجاهلت خطأ answer() قديم: {e}")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"صار خطأ وتم تجاهله حتى يضل البوت شغال: {context.error}")


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يبعت نسخة من ملف قاعدة البيانات الحالي مباشرة - لأنو الخطة
    المجانية بـ Render بتمسح الملفات المحلية عند أي restart/redeploy/نوم،
    فلازم تاخد نسخة احتياطية بانتظام."""
    if not os.path.exists(db.DB_PATH):
        await update.message.reply_text("ما في قاعدة بيانات لسا، لسا ما ضفت أي ملف.")
        return
    await update.message.reply_document(
        document=open(db.DB_PATH, "rb"),
        filename="database.db",
        caption="نسخة قاعدة البيانات الحالية 📦",
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📤 إضافة ملف جديد (txt)", callback_data="start_sendtxt")],
        [InlineKeyboardButton("✏️ تعديل سؤال موجود", callback_data="start_editmenu")],
    ]
    await update.message.reply_text(
        "أهلاً 👋 شو بدك تعمل؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_sendtxt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    await query.edit_message_text("تمام، ابعتلي ملف الـ .txt هلق مباشرة 📎")


async def start_editmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    keyboard = [
        [InlineKeyboardButton("🔍 بحث نصي", callback_data="editmode_search")],
        [InlineKeyboardButton("📂 تصفح (مادة ← شيت ← سؤال)", callback_data="editmode_browse")],
        [InlineKeyboardButton("🔢 رقم السؤال مباشرة", callback_data="editmode_goto")],
    ]
    await query.edit_message_text(
        "كيف بدك توصل للسؤال؟", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def editmode_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    context.user_data["awaiting"] = ("search_keyword",)
    await query.edit_message_text("اكتب كلمة من نص السؤال يلي بدك تدور عليه:")


async def editmode_goto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    context.user_data["awaiting"] = ("goto_number",)
    await query.edit_message_text("اكتب رقم السؤال:")


async def editmode_browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    subjects = db.get_all_subjects()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"browsesubj:{uuid_}:0")]
        for uuid_, name in subjects
    ]
    await query.edit_message_text(
        "اختار المادة:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------------------------------------------------------------------
# استقبال ملف txt
# ---------------------------------------------------------------------------

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("لازم يكون الملف بصيغة .txt 🙏")
        return

    tg_file = await doc.get_file()
    raw_bytes = await tg_file.download_as_bytearray()
    content = raw_bytes.decode("utf-8", errors="replace")

    sheets = p.parse_file(content)
    if not sheets:
        await update.message.reply_text(
            "ما قدرت استخرج ولا سؤال من الملف. تأكد إنو القالب مطابق للمتفق عليه."
        )
        return

    total_q = sum(len(s["questions"]) for s in sheets)
    context.user_data["pending_sheets"] = sheets

    subjects = db.get_all_subjects()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"subject:{uuid_}")]
        for uuid_, name in subjects
    ]
    await update.message.reply_text(
        f"لقيت {len(sheets)} شيت و {total_q} سؤال بالملف.\n"
        "لأي مادة يعود هاد الملف؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ---------------------------------------------------------------------------
# اختيار المادة -> بناء طابور حل التصنيفات
# ---------------------------------------------------------------------------

async def subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    subject_uuid = query.data.split(":", 1)[1]
    context.user_data["subject_uuid"] = subject_uuid

    sheets = context.user_data.get("pending_sheets", [])

    # بناء قائمة التصنيفات الخام الفريدة (broad + specific) المحتاجة حل
    raw_names = []
    seen = set()
    for s in sheets:
        for q in s["questions"]:
            for raw in (q["broad_tag_raw"], q["specific_tag_raw"]):
                if raw and raw not in seen:
                    seen.add(raw)
                    raw_names.append(raw)

    context.user_data["tag_queue"] = raw_names
    context.user_data["tag_resolution"] = {}  # raw_name -> tag_uuid
    context.user_data["queue_index"] = 0

    await query.edit_message_text("تمام، عم افحص التصنيفات...")
    await resolve_next_tag(update, context)


async def resolve_next_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    queue = context.user_data["tag_queue"]
    idx = context.user_data["queue_index"]

    existing_tags = db.get_all_tags()

    while idx < len(queue):
        raw_name = queue[idx]
        result = t.resolve_broad(raw_name, db.BROAD_PREFIX_ALIASES, existing_tags)

        if result[0] == "exact":
            context.user_data["tag_resolution"][raw_name] = result[1]
            idx += 1
            continue

        if result[0] == "new":
            new_uuid = db.create_new_tag(raw_name)
            context.user_data["tag_resolution"][raw_name] = new_uuid
            existing_tags.append((new_uuid, raw_name))
            idx += 1
            continue

        # ambiguous -> لازم نسأل المستخدم
        context.user_data["queue_index"] = idx
        candidates = result[1]
        best_uuid, best_name, best_score = candidates[0]
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ نعم، نفس التصنيف", callback_data=f"tagyes:{best_uuid}"
                ),
                InlineKeyboardButton("🆕 لأ، تصنيف جديد", callback_data="tagno"),
            ]
        ]
        text = (
            f"وجدت تصنيف مشابه لـ: «{raw_name}»\n"
            f"هل هو نفسه: «{best_name}»؟ (تشابه {best_score:.0%})"
        )
        chat = update.effective_chat
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # الطابور خلص -> ندخل كل شي بقاعدة البيانات
    context.user_data["queue_index"] = idx
    await finalize_import(update, context)


async def tag_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)

    queue = context.user_data["tag_queue"]
    idx = context.user_data["queue_index"]
    raw_name = queue[idx]

    if query.data.startswith("tagyes:"):
        tag_uuid = query.data.split(":", 1)[1]
        context.user_data["tag_resolution"][raw_name] = tag_uuid
        await query.edit_message_text(f"تمام، ربطت «{raw_name}» بالتصنيف الموجود.")
    else:
        new_uuid = db.create_new_tag(raw_name)
        context.user_data["tag_resolution"][raw_name] = new_uuid
        await query.edit_message_text(f"تمام، أنشأت تصنيف جديد: «{raw_name}» ({new_uuid}).")

    context.user_data["queue_index"] = idx + 1
    await resolve_next_tag(update, context)


# ---------------------------------------------------------------------------
# الإدخال النهائي بقاعدة البيانات
# ---------------------------------------------------------------------------

async def finalize_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheets = context.user_data["pending_sheets"]
    subject_uuid = context.user_data["subject_uuid"]
    tag_resolution = context.user_data["tag_resolution"]

    conn = db.get_connection()
    total_questions = total_answers = 0
    new_sheets = merged_sheets = 0

    try:
        for s in sheets:
            sheet_uuid, is_new = db.get_or_create_sheet(conn, subject_uuid, s["year"], s["term_text"])
            if is_new:
                new_sheets += 1
            else:
                merged_sheets += 1
            start_order = db.get_max_display_order(conn, sheet_uuid)

            for i, q in enumerate(s["questions"], start=1):
                order = start_order + i
                note = p.build_note(q["explanation"], q["attention"])
                q_uuid = db.insert_question(conn, sheet_uuid, subject_uuid, q["text"], note, order)
                total_questions += 1

                for letter, opt_text in q["options"].items():
                    label = p.LETTER_TO_LABEL.get(letter, letter)
                    is_correct = letter == q["correct_letter"]
                    db.insert_answer(conn, q_uuid, opt_text, label, is_correct)
                    total_answers += 1

                for raw in (q["broad_tag_raw"], q["specific_tag_raw"]):
                    if not raw:
                        continue
                    tag_uuid = tag_resolution.get(raw)
                    if not tag_uuid:
                        continue
                    db.link_question_tag(conn, q_uuid, tag_uuid)
                    db.link_subject_tag(conn, subject_uuid, tag_uuid)
                    db.bump_tag_statistic(conn, tag_uuid, subject_uuid)

            db.finalize_sheet_count(conn, sheet_uuid)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    chat = update.effective_chat
    summary = (
        "✅ تم الإدخال بنجاح!\n\n"
        f"شيتات جديدة: {new_sheets}\n"
        f"شيتات دُمجت مع شيت موجود أصلاً (نفس السنة/الدورة): {merged_sheets}\n"
        f"عدد الأسئلة: {total_questions}\n"
        f"عدد الإجابات: {total_answers}\n"
        f"عدد التصنيفات المستخدمة: {len(tag_resolution)}\n"
    )
    await chat.send_message(summary)
    await chat.send_document(
        document=open(db.DB_PATH, "rb"),
        filename="database.db",
        caption="نسخة احتياطية أوتوماتيكية بعد الاستيراد 📦",
    )

    context.user_data.clear()


# ---------------------------------------------------------------------------
# واجهة التحكم: البحث / التصفح / الرقم المباشر
# ---------------------------------------------------------------------------

RESULTS_PER_PAGE = 8


def _truncate(text, n=45):
    return text if len(text) <= n else text[: n - 1] + "…"


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/edit كلمة_من_السؤال  -> بحث نصي"""
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("اكتب هيك: /edit كلمة من نص السؤال")
        return
    results, total = db.search_questions_by_text(keyword, limit=RESULTS_PER_PAGE)
    if not results:
        await update.message.reply_text("ما لقيت ولا سؤال فيه هالكلمة.")
        return
    keyboard = [
        [InlineKeyboardButton(_truncate(text), callback_data=f"edit:{uuid_}")]
        for uuid_, text in results
    ]
    await update.message.reply_text(
        f"لقيت {total} نتيجة (عم اعرض أول {len(results)}):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_goto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/goto رقم_السؤال -> وصول مباشر"""
    if not context.args:
        await update.message.reply_text("اكتب هيك: /goto 42")
        return
    question_uuid = context.args[0].strip()
    q = db.get_question_by_uuid(question_uuid)
    if not q:
        await update.message.reply_text(f"ما في سؤال برقم {question_uuid}.")
        return
    await show_edit_menu(update.effective_chat, q["uuid"])


async def cmd_browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/browse -> تصفح مادة ← شيت ← سؤال"""
    subjects = db.get_all_subjects()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"browsesubj:{uuid_}:0")]
        for uuid_, name in subjects
    ]
    await update.message.reply_text(
        "اختار المادة:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def browse_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, subject_uuid, offset = query.data.split(":")
    offset = int(offset)
    sheets, total = db.get_sheets_by_subject(subject_uuid, limit=RESULTS_PER_PAGE, offset=offset)

    keyboard = [
        [
            InlineKeyboardButton(
                f"{year} - {term} ({count} سؤال)",
                callback_data=f"browsesheet:{uuid_}:{subject_uuid}:0",
            )
        ]
        for uuid_, year, term, count in sheets
    ]
    nav = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton("« السابق", callback_data=f"browsesubj:{subject_uuid}:{max(0, offset-RESULTS_PER_PAGE)}")
        )
    if offset + RESULTS_PER_PAGE < total:
        nav.append(
            InlineKeyboardButton("التالي »", callback_data=f"browsesubj:{subject_uuid}:{offset+RESULTS_PER_PAGE}")
        )
    if nav:
        keyboard.append(nav)

    await query.edit_message_text("اختار الشيت:", reply_markup=InlineKeyboardMarkup(keyboard))


async def browse_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, sheet_uuid, subject_uuid, offset = query.data.split(":")
    offset = int(offset)
    questions, total = db.get_questions_by_sheet(
        sheet_uuid, subject_uuid=subject_uuid, limit=RESULTS_PER_PAGE, offset=offset
    )

    keyboard = [
        [InlineKeyboardButton(f"{order}. {_truncate(text)}", callback_data=f"edit:{uuid_}")]
        for uuid_, text, order in questions
    ]
    nav = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton("« السابق", callback_data=f"browsesheet:{sheet_uuid}:{subject_uuid}:{max(0, offset-RESULTS_PER_PAGE)}")
        )
    if offset + RESULTS_PER_PAGE < total:
        nav.append(
            InlineKeyboardButton("التالي »", callback_data=f"browsesheet:{sheet_uuid}:{subject_uuid}:{offset+RESULTS_PER_PAGE}")
        )
    if nav:
        keyboard.append(nav)

    await query.edit_message_text("اختار السؤال:", reply_markup=InlineKeyboardMarkup(keyboard))


async def edit_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    question_uuid = query.data.split(":", 1)[1]
    await show_edit_menu(update.effective_chat, question_uuid, edit_message=query)


async def show_edit_menu(chat, question_uuid, edit_message=None):
    q = db.get_question_by_uuid(question_uuid)
    if not q:
        target = edit_message.edit_message_text if edit_message else chat.send_message
        await target("هاد السؤال مش موجود.")
        return

    keyboard = [
        [InlineKeyboardButton("📝 نص السؤال", callback_data=f"editfield:text:{question_uuid}")],
        [InlineKeyboardButton("✅ الإجابات", callback_data=f"editfield:answers:{question_uuid}")],
        [InlineKeyboardButton("🏷️ التصنيف", callback_data=f"editfield:tags:{question_uuid}")],
        [InlineKeyboardButton("📌 الملاحظة", callback_data=f"editfield:note:{question_uuid}")],
    ]
    text = f"سؤال #{question_uuid}:\n{q['text']}\n\nشو بدك تعدل؟"
    if edit_message:
        await edit_message.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ---------------------------------------------------------------------------
# تعديل الحقول
# ---------------------------------------------------------------------------

async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, field, question_uuid = query.data.split(":")

    if field == "text":
        context.user_data["awaiting"] = ("question_text", question_uuid)
        await query.edit_message_text("ابعتلي نص السؤال الجديد:")

    elif field == "note":
        context.user_data["awaiting"] = ("note_text", question_uuid)
        await query.edit_message_text("ابعتلي نص الملاحظة الجديد (شرح + انتبه):")

    elif field == "answers":
        await show_answers_menu(query, question_uuid)

    elif field == "tags":
        await show_tags_menu(query, question_uuid)


async def show_answers_menu(query, question_uuid):
    answers = db.get_answers_for_question(question_uuid)
    keyboard = []
    for uuid_, text, label, is_correct in answers:
        mark = "✅" if is_correct else "▫️"
        keyboard.append(
            [InlineKeyboardButton(f"{mark} {label}. {_truncate(text, 35)}", callback_data=f"ansedit:{uuid_}:{question_uuid}")]
        )
        keyboard.append(
            [InlineKeyboardButton(f"⭐ اجعل {label} هي الصحيحة", callback_data=f"anscorrect:{uuid_}:{question_uuid}")]
        )
    keyboard.append([InlineKeyboardButton("« رجوع", callback_data=f"edit:{question_uuid}")])
    await query.edit_message_text(
        "اضغط على خيار لتعديل نصه، أو اجعله الإجابة الصحيحة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def answer_edit_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, answer_uuid, question_uuid = query.data.split(":")
    context.user_data["awaiting"] = ("answer_text", answer_uuid, question_uuid)
    await query.edit_message_text("ابعتلي النص الجديد لهاد الخيار:")


async def answer_set_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, answer_uuid, question_uuid = query.data.split(":")
    db.set_correct_answer(question_uuid, answer_uuid)
    await show_answers_menu(query, question_uuid)


async def show_tags_menu(query, question_uuid):
    tags = db.get_tags_for_question(question_uuid)
    keyboard = [
        [InlineKeyboardButton(f"❌ حذف: {name}", callback_data=f"tagrm:{tag_uuid}:{question_uuid}")]
        for tag_uuid, name in tags
    ]
    keyboard.append([InlineKeyboardButton("➕ إضافة تصنيف", callback_data=f"tagadd:{question_uuid}")])
    keyboard.append([InlineKeyboardButton("« رجوع", callback_data=f"edit:{question_uuid}")])
    current = "، ".join(name for _, name in tags) if tags else "(بدون تصنيف حالياً)"
    await query.edit_message_text(
        f"التصنيفات الحالية: {current}\n\nشو بدك تعمل؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def tag_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, tag_uuid, question_uuid = query.data.split(":")
    db.remove_question_tag(question_uuid, tag_uuid)
    await show_tags_menu(query, question_uuid)


async def tag_add_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    question_uuid = query.data.split(":", 1)[1]
    context.user_data["awaiting"] = ("new_tag_name", question_uuid)
    await query.edit_message_text("ابعتلي اسم التصنيف يلي بدك تضيفه:")


async def tag_add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رد على سؤال 'هل هو نفس التصنيف الموجود؟' وقت إضافة تصنيف من قائمة التعديل."""
    query = update.callback_query
    await _safe_answer(query)
    parts = query.data.split(":")
    action = parts[0]  # edittagyes / edittagno
    question_uuid = parts[-1]

    if action == "edittagyes":
        tag_uuid = parts[1]
    else:
        raw_name = context.user_data.get("pending_new_tag_name", "")
        tag_uuid = db.create_new_tag(raw_name)

    db.add_question_tag_full(question_uuid, tag_uuid)
    await query.edit_message_text("تمام، انضاف التصنيف ✅")
    await show_edit_menu(update.effective_chat, question_uuid)


# ---------------------------------------------------------------------------
# استقبال النصوص العادية (لما نكون بانتظار إدخال من المستخدم)
# ---------------------------------------------------------------------------

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    awaiting = context.user_data.get("awaiting")
    if not awaiting:
        return  # مش بانتظار شي، تجاهل

    kind = awaiting[0]
    new_text = update.message.text.strip()

    if kind == "search_keyword":
        context.user_data["awaiting"] = None
        results, total = db.search_questions_by_text(new_text, limit=RESULTS_PER_PAGE)
        if not results:
            await update.message.reply_text("ما لقيت ولا سؤال فيه هالكلمة.")
            return
        keyboard = [
            [InlineKeyboardButton(_truncate(text), callback_data=f"edit:{uuid_}")]
            for uuid_, text in results
        ]
        await update.message.reply_text(
            f"لقيت {total} نتيجة (عم اعرض أول {len(results)}):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif kind == "goto_number":
        context.user_data["awaiting"] = None
        q = db.get_question_by_uuid(new_text)
        if not q:
            await update.message.reply_text(f"ما في سؤال برقم {new_text}.")
            return
        await show_edit_menu(update.effective_chat, q["uuid"])

    elif kind == "question_text":
        question_uuid = awaiting[1]
        db.update_question_text(question_uuid, new_text)
        context.user_data["awaiting"] = None
        await update.message.reply_text("تمام، تحدّث نص السؤال ✅")
        await show_edit_menu(update.effective_chat, question_uuid)

    elif kind == "note_text":
        question_uuid = awaiting[1]
        db.update_note(question_uuid, new_text)
        context.user_data["awaiting"] = None
        await update.message.reply_text("تمام، تحدّثت الملاحظة ✅")
        await show_edit_menu(update.effective_chat, question_uuid)

    elif kind == "answer_text":
        answer_uuid, question_uuid = awaiting[1], awaiting[2]
        db.update_answer_text(answer_uuid, new_text)
        context.user_data["awaiting"] = None
        await update.message.reply_text("تمام، تحدّث نص الخيار ✅")
        keyboard = [[InlineKeyboardButton("👀 عرض الإجابات", callback_data=f"editfield:answers:{question_uuid}")]]
        await update.message.reply_text("رجعلك للقائمة:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif kind == "new_tag_name":
        question_uuid = awaiting[1]
        context.user_data["awaiting"] = None
        context.user_data["pending_new_tag_name"] = new_text

        existing_tags = db.get_all_tags()
        result = t.resolve_broad(new_text, db.BROAD_PREFIX_ALIASES, existing_tags)

        if result[0] == "exact":
            db.add_question_tag_full(question_uuid, result[1])
            await update.message.reply_text(f"لقيت تطابق تام، ضفت التصنيف: {result[2]} ✅")
            await show_edit_menu(update.effective_chat, question_uuid)

        elif result[0] == "ambiguous":
            best_uuid, best_name, best_score = result[1][0]
            keyboard = [[
                InlineKeyboardButton("✅ نعم نفسه", callback_data=f"edittagyes:{best_uuid}:{question_uuid}"),
                InlineKeyboardButton("🆕 لأ جديد", callback_data=f"edittagno:{question_uuid}"),
            ]]
            await update.message.reply_text(
                f"في تصنيف مشابه: «{best_name}» (تشابه {best_score:.0%}) — هل هو نفسه؟",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            new_uuid = db.create_new_tag(new_text)
            db.add_question_tag_full(question_uuid, new_uuid)
            await update.message.reply_text(f"أنشأت تصنيف جديد: «{new_text}» وضفته ✅")
            await show_edit_menu(update.effective_chat, question_uuid)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN مش موجود. تأكد من ملف .env")

    db.init_db()

    threading.Thread(target=start_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("goto", cmd_goto))
    app.add_handler(CommandHandler("browse", cmd_browse))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    app.add_handler(CallbackQueryHandler(start_sendtxt, pattern=r"^start_sendtxt$"))
    app.add_handler(CallbackQueryHandler(start_editmenu, pattern=r"^start_editmenu$"))
    app.add_handler(CallbackQueryHandler(editmode_search, pattern=r"^editmode_search$"))
    app.add_handler(CallbackQueryHandler(editmode_goto, pattern=r"^editmode_goto$"))
    app.add_handler(CallbackQueryHandler(editmode_browse, pattern=r"^editmode_browse$"))
    app.add_handler(CallbackQueryHandler(subject_chosen, pattern=r"^subject:"))
    app.add_handler(CallbackQueryHandler(tag_decision, pattern=r"^tag(yes|no)"))
    app.add_handler(CallbackQueryHandler(browse_subject, pattern=r"^browsesubj:"))
    app.add_handler(CallbackQueryHandler(browse_sheet, pattern=r"^browsesheet:"))
    app.add_handler(CallbackQueryHandler(edit_pick, pattern=r"^edit:"))
    app.add_handler(CallbackQueryHandler(edit_field, pattern=r"^editfield:"))
    app.add_handler(CallbackQueryHandler(answer_edit_pick, pattern=r"^ansedit:"))
    app.add_handler(CallbackQueryHandler(answer_set_correct, pattern=r"^anscorrect:"))
    app.add_handler(CallbackQueryHandler(tag_remove, pattern=r"^tagrm:"))
    app.add_handler(CallbackQueryHandler(tag_add_prompt, pattern=r"^tagadd:"))
    app.add_handler(CallbackQueryHandler(tag_add_confirm, pattern=r"^edittag(yes|no)"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    app.add_error_handler(on_error)

    logger.info("البوت شغال...")
    app.run_polling()



if __name__ == "__main__":
    main()
