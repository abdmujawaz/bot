// ---------------------------------------------------------------------------
// app.js — منطق الـ Mini App بالكامل (بدون أي build step، جافاسكربت عادي)
// ---------------------------------------------------------------------------

const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) {
  tg.ready();
  tg.expand();
}

const screenEl = document.getElementById("screen");
const titleEl = document.getElementById("screenTitle");
const eyebrowEl = document.getElementById("eyebrow");
const backBtn = document.getElementById("backBtn");
const noteModal = document.getElementById("noteModal");
const noteBody = document.getElementById("noteBody");
const noteCloseBtn = document.getElementById("noteCloseBtn");

let historyStack = [];

function pushView(view) {
  historyStack.push(view);
  renderCurrent();
}

function goBack() {
  if (historyStack.length > 1) {
    historyStack.pop();
    renderCurrent();
  }
}

function renderCurrent() {
  const view = historyStack[historyStack.length - 1];
  titleEl.textContent = view.title;
  eyebrowEl.textContent = view.eyebrow || "";
  backBtn.classList.toggle("visible", historyStack.length > 1);
  view.render();
}

backBtn.addEventListener("click", goBack);
noteCloseBtn.addEventListener("click", () => noteModal.classList.add("hidden"));
noteModal.addEventListener("click", (e) => {
  if (e.target === noteModal) noteModal.classList.add("hidden");
});

async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

function showSpinner() {
  screenEl.innerHTML = '<div class="spinner"></div>';
}

function showMessage(msg) {
  screenEl.innerHTML = `<div class="state-msg">${msg}</div>`;
}

async function safeLoad(loaderFn, emptyMsg) {
  showSpinner();
  try {
    await loaderFn();
  } catch (err) {
    console.error(err);
    showMessage("صار خطأ بجلب البيانات. جرب مرة ثانية.");
  }
}

// ---------------------------------------------------------------------------
// الشاشة الرئيسية: اختيار طريقة التصفح
// ---------------------------------------------------------------------------

function renderHome() {
  screenEl.innerHTML = `
    <div class="mode-grid">
      <div class="mode-card" id="modeSheet">
        <h2>📚 الدورات الامتحانية</h2>
      </div>
      <div class="mode-card" id="modeTag">
        <h2>🏷️ التصنيفات</h2>
      </div>
    </div>
  `;
  document.getElementById("modeSheet").onclick = () => pushView(allSheetsView());
  document.getElementById("modeTag").onclick = () =>
    pushView(subjectsView("tag"));
}

// ---------------------------------------------------------------------------
// اختيار المادة (لمسار التصنيف بس)
// ---------------------------------------------------------------------------

function subjectsView(mode) {
  return {
    title: "اختر المادة",
    eyebrow: "تصفح حسب التصنيف",
    render: () => safeLoad(() => renderSubjects(mode)),
  };
}

async function renderSubjects(mode) {
  const subjects = await apiGet("/api/subjects");
  if (!subjects.length) return showMessage("ما في مواد مضافة لسا.");
  screenEl.innerHTML = `<div class="card-list" id="list"></div>`;
  const list = document.getElementById("list");
  subjects.forEach((s) => {
    const tile = makeTile(s.name, `عدد الأسئلة: ${s.questions_count}`);
    tile.onclick = () => pushView(tagsView(s));
    list.appendChild(tile);
  });
}

function makeTile(title, sub, rankNum) {
  const div = document.createElement("div");
  div.className = "tile";
  div.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;">
      ${rankNum ? `<div class="rank-num">${rankNum}</div>` : ""}
      <div>
        <div class="tile-title">${escapeHtml(title)}</div>
        ${sub ? `<div class="tile-sub">${escapeHtml(sub)}</div>` : ""}
      </div>
    </div>
    <div class="tile-chevron">‹</div>
  `;
  return div;
}

// ---------------------------------------------------------------------------
// وضع الشيت: تختار التاريخ مباشرة (بدون ما تختار مادة الأول)، وبتطلع كل
// أسئلة كل المواد يلي عندها نفس التاريخ، مقسّمة بعنوان لكل مادة.
// ---------------------------------------------------------------------------

function allSheetsView() {
  return {
    title: "اختر الشيت",
    eyebrow: "حسب التاريخ",
    render: () => safeLoad(() => renderAllSheets()),
  };
}

async function renderAllSheets() {
  const data = await apiGet("/api/sheets?limit=200");
  if (!data.sheets.length) return showMessage("ما في شيتات مضافة لسا.");
  screenEl.innerHTML = `<div class="card-list" id="list"></div>`;
  const list = document.getElementById("list");
  data.sheets.forEach((sh) => {
    const label = `${sh.year || "—"} — ${sh.term || ""}`;
    const tile = makeTile(label, `عدد الأسئلة: ${sh.questions_count}`);
    tile.onclick = () => pushView(sheetGroupedQuestionsView(sh));
    list.appendChild(tile);
  });
}

function sheetGroupedQuestionsView(sheet) {
  return {
    title: `${sheet.year || ""} — ${sheet.term || ""}`,
    eyebrow: "كل المواد",
    render: () =>
      safeLoad(async () => {
        const detail = await apiGet(`/api/sheets/${sheet.uuid}`);
        renderGroupedQuestions(detail);
      }),
  };
}

// ---------------------------------------------------------------------------
// وضع التصنيف: عرض التصنيفات مرتبة حسب الأولوية
// ---------------------------------------------------------------------------

function tagsView(subject) {
  return {
    title: subject.name,
    eyebrow: "التصنيفات — حسب الأولوية",
    render: () => safeLoad(() => renderTags(subject)),
  };
}

async function renderTags(subject) {
  const tags = await apiGet(`/api/subjects/${subject.uuid}/tags`);
  if (!tags.length) return showMessage("ما في تصنيفات لهاي المادة لسا.");
  screenEl.innerHTML = `<div class="card-list" id="list"></div>`;
  const list = document.getElementById("list");
  tags.forEach((tg_, i) => {
    const tile = makeTile(tg_.name, `تكرر ${tg_.count} مرة`, i + 1);
    tile.onclick = () => pushView(tagQuestionsView(subject, tg_));
    list.appendChild(tile);
  });
}

function tagQuestionsView(subject, tag) {
  return {
    title: tag.name,
    eyebrow: subject.name,
    render: () =>
      safeLoad(async () => {
        const data = await apiGet(
          `/api/subjects/${subject.uuid}/tags/${tag.uuid}/questions?limit=300`
        );
        renderQuestions(data.questions, { showYearChip: true });
      }),
  };
}

// ---------------------------------------------------------------------------
// عرض قائمة الأسئلة (نمط اختبار: اضغط جواب يبين صح/غلط)
// ---------------------------------------------------------------------------

function buildQuestionCard(q, { showYearChip }) {
  const card = document.createElement("div");
  card.className = "q-card";

  const yearChip =
    showYearChip && q.sheet_year
      ? `<span class="year-chip">${escapeHtml(String(q.sheet_year))}</span>`
      : "";
  const hasNote = q.note && q.note.trim().length > 0;

  card.innerHTML = `
    <div class="q-head">
      <div class="q-text">${escapeHtml(q.text)}</div>
      <div class="q-meta">
        ${yearChip}
        <button class="note-btn" ${hasNote ? "" : "disabled"} title="الشرح">!</button>
      </div>
    </div>
    <div class="answers"></div>
  `;

  card.querySelector(".note-btn").onclick = () => {
    if (!hasNote) return;
    noteBody.textContent = q.note;
    noteModal.classList.remove("hidden");
  };

  const answersEl = card.querySelector(".answers");
  let answered = false;

  q.answers.forEach((a) => {
    const btn = document.createElement("button");
    btn.className = "answer-btn";
    btn.innerHTML = `<span class="label">${escapeHtml(a.label || "")}</span><span>${escapeHtml(a.text)}</span>`;
    btn.onclick = () => {
      if (answered) return;
      answered = true;
      const allBtns = answersEl.querySelectorAll(".answer-btn");
      allBtns.forEach((b) => (b.disabled = true));

      if (a.is_correct) {
        btn.classList.add("correct");
      } else {
        btn.classList.add("wrong");
        const correctBtn = [...allBtns].find(
          (_, idx) => q.answers[idx].is_correct
        );
        if (correctBtn) correctBtn.classList.add("correct");
        allBtns.forEach((b) => {
          if (b !== btn && !b.classList.contains("correct")) {
            b.classList.add("disabled-choice");
          }
        });
      }
    };
    answersEl.appendChild(btn);
  });

  return card;
}

function renderQuestions(questions, { showYearChip }) {
  if (!questions.length) return showMessage("ما في أسئلة هون.");
  screenEl.innerHTML = `<div class="q-list" id="qlist"></div>`;
  const qlist = document.getElementById("qlist");
  questions.forEach((q) => {
    qlist.appendChild(buildQuestionCard(q, { showYearChip }));
  });
}

// شاشة الشيت الكاملة: كل المواد المشتركة بنفس التاريخ، كل مادة بعنوانها
// وتحته أسئلتها بس (مرتبة حسب ترتيبها الطبيعي جوا الشيت).
function renderGroupedQuestions(detail) {
  if (!detail.subjects.length || !detail.questions.length) {
    return showMessage("ما في أسئلة بهاد الشيت.");
  }

  screenEl.innerHTML = `<div class="q-list" id="qlist"></div>`;
  const qlist = document.getElementById("qlist");

  detail.subjects.forEach((subject) => {
    const subjectQuestions = detail.questions
      .filter((q) => q.subject_uuid === subject.uuid)
      .sort((a, b) => a.display_order - b.display_order);
    if (!subjectQuestions.length) return;

    const header = document.createElement("div");
    header.className = "subject-header";
    header.innerHTML = `<span>${escapeHtml(subject.name)}</span><span class="subject-header-count">${subjectQuestions.length} سؤال</span>`;
    qlist.appendChild(header);

    subjectQuestions.forEach((q) => {
      qlist.appendChild(buildQuestionCard(q, { showYearChip: false }));
    });
  });
}

// ---------------------------------------------------------------------------
// أدوات مساعدة
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// نقطة الانطلاق
// ---------------------------------------------------------------------------

pushView({
  title: "بنك الأسئلة",
  eyebrow: "",
  render: renderHome,
});
