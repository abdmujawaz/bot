"""
api.py
سيرفر FastAPI يوفر endpoints للقراءة فقط (read-only) لصالح الـ Mini App.
بيشتغل جوا نفس بروسس البوت (bot.py) على خيط منفصل عن طريق uvicorn، وبيقرأ
مباشرة من نفس ملف database.db يلي البوت عم يكتب فيه - بدون أي خدمة Render
إضافية وبدون مشكلة مزامنة بين نسختين.
"""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db

app = FastAPI(title="Question Bank API")

# مسموح لأي أصل (origin) يطلب - لازم هيك لأنو الـ Mini App بتنفتح جوا
# تطبيق تيليجرام (Web View) وممكن تجي من أي دومين/بروتوكول.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health():
    """health-check بسيط (نفس وظيفة السيرفر القديم) حتى يعتبر Render التطبيق شغال."""
    return {"status": "ok", "message": "البوت شغال ✅"}


@app.get("/api/subjects")
def api_subjects():
    subjects = db.get_all_subjects()
    return [{"uuid": uuid_, "name": name} for uuid_, name in subjects]


@app.get("/api/subjects/{subject_uuid}/sheets")
def api_subject_sheets(
    subject_uuid: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    sheets, total = db.get_sheets_by_subject(subject_uuid, limit=limit, offset=offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sheets": [
            {"uuid": uuid_, "year": year, "term": term, "questions_count": count}
            for uuid_, year, term, count in sheets
        ],
    }


@app.get("/api/sheets/{sheet_uuid}")
def api_sheet_detail(sheet_uuid: str, subject_uuid: Optional[str] = None):
    """يرجّع الشيت كاملة: معلوماتها + كل المواد المشتركة فيها + كل أسئلتها
    (بإجاباتها وتصنيفاتها). إذا انعطى ?subject_uuid=... بيقتصر عرض
    الأسئلة على هاي المادة بس."""
    detail = db.get_sheet_full_detail(sheet_uuid, subject_uuid=subject_uuid)
    if detail is None:
        raise HTTPException(status_code=404, detail="الشيت مش موجودة")
    return detail


@app.get("/api/subjects/{subject_uuid}/tags")
def api_subject_tags(subject_uuid: str):
    """تصنيفات المادة، مرتبة حسب الأولوية (الأكتر تكراراً بالامتحانات أولاً)."""
    tags = db.get_tags_for_subject(subject_uuid)
    return [{"uuid": uuid_, "name": name, "count": count} for uuid_, name, count in tags]


@app.get("/api/subjects/{subject_uuid}/tags/{tag_uuid}/questions")
def api_tag_questions(
    subject_uuid: str,
    tag_uuid: str,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """كل أسئلة مادة معينة تحت تصنيف معين، مرتبة حسب الأولوية (الأحدث أولاً)."""
    questions, total = db.get_questions_by_tag(
        subject_uuid, tag_uuid, limit=limit, offset=offset
    )
    return {"total": total, "questions": questions}


@app.get("/api/stats/overview")
def api_stats_overview():
    return db.get_overview_stats()


@app.get("/api/stats/subjects/{subject_uuid}")
def api_subject_stats(subject_uuid: str):
    stats = db.get_subject_stats(subject_uuid)
    if stats is None:
        raise HTTPException(status_code=404, detail="المادة مش موجودة")
    return stats


# لازم هاد آخر شي بالملف - أي مسار API لازم يتسجل قبل mount الـ static files
# حتى ما يبلعها الـ StaticFiles catch-all.
app.mount("/webapp", StaticFiles(directory="static", html=True), name="webapp")
