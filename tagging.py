"""
tagging.py
منطق مطابقة أسماء التصنيفات (Tags) القادمة من الملف مع التصنيفات
الموجودة أصلاً بقاعدة البيانات، حسب القرار المتفق عليه:

    - تطابق تام (بعد التطبيع) -> استخدام تلقائي بدون سؤال
    - تشابه قريب (منطقة الشك) -> لازم تأكيد من المستخدم عبر البوت
    - ما في أي تشابه -> تصنيف جديد تلقائياً

التطبيع بيشيل التشكيل، يوحّد أشكال الألف والهمزة والتاء المربوطة،
ويشيل المسافات الزايدة - حتى فرق إملائي بسيط ما يفوت من تحت المطابقة التامة.
"""

import re
import difflib

EXACT_THRESHOLD = 0.97  # فوق هيك = تطابق تام (يشمل فرق إملائي بسيط جداً)
FUZZY_LOW_THRESHOLD = 0.72  # تحت هيك = تصنيف جديد بدون سؤال


def normalize(text):
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"[\u064B-\u065F\u0670]", "", t)  # إزالة التشكيل
    t = re.sub(r"[إأآا]", "ا", t)
    t = re.sub(r"ى", "ي", t)
    t = re.sub(r"ة", "ه", t)
    t = re.sub(r"\s+", " ", t)
    return t.lower().strip()


def similarity(a, b):
    """
    تشابه محسّن: بيراعي حالة "احتواء" نص قصير جوا نص أطول (متل
    'الحمى المالطية' جوا 'داء البروسيلا (الحمى المالطية)')، مش بس
    التشابه الحرفي للنص كامل بكامل، لأنو هاي أهم حالة عملية بنواجهها.
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0

    base_ratio = difflib.SequenceMatcher(None, na, nb).ratio()

    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    containment_ratio = 0.0
    if shorter in longer:
        coverage = len(shorter) / len(longer)
        containment_ratio = 0.9 + 0.1 * coverage

    return max(base_ratio, containment_ratio)


def match_tag(raw_name, existing_tags):
    """
    existing_tags: list[(uuid, name)]
    يرجع tuple:
      ("exact", uuid, name)              -> تطابق تام، استخدام مباشر
      ("ambiguous", [(uuid, name, score), ...])  -> لازم تأكيد المستخدم (أعلى 3 نتائج)
      ("new", None, None)                -> ما في تشابه، تصنيف جديد
    """
    scored = [(uuid_, name, similarity(raw_name, name)) for uuid_, name in existing_tags]
    scored.sort(key=lambda x: x[2], reverse=True)

    if not scored:
        return ("new", None, None)

    best_uuid, best_name, best_score = scored[0]

    if best_score >= EXACT_THRESHOLD:
        return ("exact", best_uuid, best_name)

    if best_score >= FUZZY_LOW_THRESHOLD:
        candidates = [c for c in scored if c[2] >= FUZZY_LOW_THRESHOLD][:3]
        return ("ambiguous", candidates, None)

    return ("new", None, None)


def resolve_broad(raw_name, alias_map, existing_tags):
    """
    للتصنيفات العريضة (قبل الشرطة) بيكون في مرادفات لفظية مختلفة تماماً
    عن بعضها (متلاً 'قسم الجراثيم' و 'الأخماج الجرثومية' لنفس المعنى)
    ما فيها تشابه نصي حرفي إطلاقاً، فبنعتمد أول شي على خريطة مرادفات
    يدوية بدل التشابه النصي، وبنرجع لمنطق match_tag العادي إذا ما لقينا
    شي بالخريطة.
    """
    key = normalize(raw_name)
    for alias, canonical in alias_map.items():
        if normalize(alias) == key:
            for uuid_, name in existing_tags:
                if normalize(name) == normalize(canonical):
                    return ("exact", uuid_, name)
    return match_tag(raw_name, existing_tags)
