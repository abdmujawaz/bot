BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "Answer" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"text"	TEXT,
	"answerLabel"	TEXT,
	"question_uuid"	TEXT,
	"isCorrect"	INTEGER NOT NULL DEFAULT 0 CHECK("isCorrect" IN (0, 1)),
	PRIMARY KEY("id"),
	FOREIGN KEY("question_uuid") REFERENCES "Question"("uuid") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS "Collage" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"name"	TEXT,
	PRIMARY KEY("id")
);
CREATE TABLE IF NOT EXISTS "Question" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"text"	TEXT,
	"display_order"	INTEGER,
	"sheet_uuid"	TEXT,
	"note"	TEXT,
	"answersCleanText"	TEXT,
	"questionType"	TEXT,
	"subject_uuid"	TEXT,
	PRIMARY KEY("id"),
	FOREIGN KEY("sheet_uuid") REFERENCES "Sheet"("uuid") ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY("subject_uuid") REFERENCES "Subject"("uuid") ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS "QuestionTag" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"question_uuid"	TEXT,
	"tag_uuid"	TEXT,
	PRIMARY KEY("id"),
	UNIQUE("question_uuid","tag_uuid"),
	FOREIGN KEY("question_uuid") REFERENCES "Question"("uuid") ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY("tag_uuid") REFERENCES "Tag"("uuid") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS "Sheet" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"text"	TEXT,
	"languageDirection"	TEXT,
	"term"	TEXT,
	"year"	INTEGER,
	"term_uuid"	TEXT,
	"notes"	TEXT,
	"type"	TEXT,
	"questionsCount"	INTEGER DEFAULT 0,
	"subject_uuid"	TEXT,
	"examDate"	TEXT,
	PRIMARY KEY("id"),
	FOREIGN KEY("subject_uuid") REFERENCES "Subject"("uuid") ON DELETE SET NULL ON UPDATE CASCADE,
	FOREIGN KEY("term_uuid") REFERENCES "Term"("uuid") ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS "Subject" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"name"	TEXT,
	"maxMark"	REAL,
	"term_uuid"	TEXT,
	"banksCount"	INTEGER DEFAULT 0,
	"examsCount"	INTEGER DEFAULT 0,
	"questionsCount"	INTEGER DEFAULT 0,
	"about"	TEXT,
	PRIMARY KEY("id"),
	FOREIGN KEY("term_uuid") REFERENCES "Term"("uuid") ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS "SubjectTag" (
	"id"	INTEGER,
	"subject_uuid"	TEXT NOT NULL,
	"tag_uuid"	TEXT NOT NULL,
	PRIMARY KEY("id"),
	UNIQUE("subject_uuid","tag_uuid"),
	FOREIGN KEY("subject_uuid") REFERENCES "Subject"("uuid") ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY("tag_uuid") REFERENCES "Tag"("uuid") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS "Tag" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"name"	TEXT,
	PRIMARY KEY("id")
);
CREATE TABLE IF NOT EXISTS "TagStatistic" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"banksCount"	INTEGER DEFAULT 0,
	"examsCount"	INTEGER DEFAULT 0,
	"count"	INTEGER DEFAULT 0,
	"category"	TEXT,
	"name"	TEXT,
	"tag_uuid"	TEXT,
	"subject_uuid"	TEXT,
	PRIMARY KEY("id"),
	FOREIGN KEY("subject_uuid") REFERENCES "Subject"("uuid") ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY("tag_uuid") REFERENCES "Tag"("uuid") ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS "Term" (
	"id"	INTEGER,
	"uuid"	TEXT NOT NULL UNIQUE,
	"name"	TEXT,
	"year"	INTEGER,
	"term"	TEXT,
	"termType"	TEXT,
	"collage_uuid"	TEXT,
	PRIMARY KEY("id"),
	FOREIGN KEY("collage_uuid") REFERENCES "Collage"("uuid") ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_answer_question_uuid" ON "Answer" ("question_uuid");
CREATE INDEX IF NOT EXISTS "idx_question_sheet_uuid" ON "Question" ("sheet_uuid");
CREATE INDEX IF NOT EXISTS "idx_question_subject_uuid" ON "Question" ("subject_uuid");
CREATE INDEX IF NOT EXISTS "idx_questiontag_q" ON "QuestionTag" ("question_uuid");
CREATE INDEX IF NOT EXISTS "idx_questiontag_t" ON "QuestionTag" ("tag_uuid");
CREATE INDEX IF NOT EXISTS "idx_sheet_subject_uuid" ON "Sheet" ("subject_uuid");
CREATE INDEX IF NOT EXISTS "idx_sheet_term_uuid" ON "Sheet" ("term_uuid");
CREATE INDEX IF NOT EXISTS "idx_subject_term_uuid" ON "Subject" ("term_uuid");
CREATE INDEX IF NOT EXISTS "idx_subjecttag_s" ON "SubjectTag" ("subject_uuid");
CREATE INDEX IF NOT EXISTS "idx_subjecttag_t" ON "SubjectTag" ("tag_uuid");
CREATE INDEX IF NOT EXISTS "idx_term_collage_uuid" ON "Term" ("collage_uuid");
COMMIT;
