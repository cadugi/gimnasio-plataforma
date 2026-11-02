-- Bajas definitivas y mantenimientos (bajas temporales). Aditiva: no toca datos existentes.
CREATE TABLE withdrawals(
 id TEXT PRIMARY KEY,
 reference TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL CHECK(kind IN ('PERMANENT','MAINTENANCE')),
 member_id TEXT REFERENCES members(id),
 document_fingerprint TEXT NOT NULL,
 snapshot_enc TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL,
 pdf_enc TEXT NOT NULL,
 pdf_hash TEXT NOT NULL,
 signature_enc TEXT NOT NULL,
 evidence_enc TEXT NOT NULL,
 last_day TEXT NOT NULL,
 effective_date TEXT NOT NULL,
 fee_cents_per_month INTEGER NOT NULL DEFAULT 500,
 state TEXT NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','ACCEPTED','REJECTED')),
 decided_at TEXT,
 decided_actor TEXT,
 reject_reason_enc TEXT,
 returned_at TEXT,
 return_months INTEGER,
 return_fee_cents INTEGER,
 return_renewal_cents INTEGER,
 return_actor TEXT,
 created_at TEXT NOT NULL
);
CREATE INDEX withdrawals_state ON withdrawals(state,created_at);
CREATE INDEX withdrawals_document ON withdrawals(document_fingerprint,state);
CREATE INDEX withdrawals_member ON withdrawals(member_id,state);
CREATE TRIGGER withdrawal_signed_immutable BEFORE UPDATE OF id,reference,kind,member_id,document_fingerprint,snapshot_enc,snapshot_hash,pdf_enc,pdf_hash,signature_enc,evidence_enc,last_day,effective_date,fee_cents_per_month,created_at ON withdrawals BEGIN SELECT RAISE(ABORT,'immutable signed withdrawal'); END;
CREATE TRIGGER withdrawal_no_delete BEFORE DELETE ON withdrawals BEGIN SELECT RAISE(ABORT,'immutable signed withdrawal'); END;
CREATE TABLE withdrawal_email_jobs(
 id TEXT PRIMARY KEY,
 withdrawal_id TEXT NOT NULL REFERENCES withdrawals(id),
 state TEXT NOT NULL DEFAULT 'QUEUED',
 attempts INTEGER NOT NULL DEFAULT 0,
 next_try_at TEXT,
 sent_at TEXT,
 last_error TEXT,
 created_at TEXT NOT NULL
);
CREATE INDEX withdrawal_email_jobs_state ON withdrawal_email_jobs(state,next_try_at);
