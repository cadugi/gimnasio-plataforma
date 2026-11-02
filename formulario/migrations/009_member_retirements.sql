CREATE TABLE member_retirements (
 id TEXT PRIMARY KEY,
 member_id TEXT NOT NULL REFERENCES members(id),
 mode TEXT NOT NULL CHECK(mode IN ('INNUX','PORTAL_ONLY')),
 state TEXT NOT NULL CHECK(state IN ('QUEUED','RUNNING','REVIEW_REQUIRED','COMPLETED','CANCELLED')),
 actor TEXT NOT NULL,
 reason_enc TEXT NOT NULL,
 options_enc TEXT NOT NULL,
 archive_enc TEXT NOT NULL,
 result_enc TEXT,
 device_id TEXT REFERENCES innux_devices(id),
 lease_until INTEGER,
 error_code TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 completed_at TEXT
);
CREATE UNIQUE INDEX one_open_retirement ON member_retirements(member_id) WHERE state<>'CANCELLED';
CREATE INDEX member_retirements_queue ON member_retirements(state,created_at);
CREATE TRIGGER member_retirements_archive_immutable BEFORE UPDATE OF member_id,mode,actor,reason_enc,archive_enc,created_at ON member_retirements BEGIN SELECT RAISE(ABORT,'immutable retirement archive'); END;
CREATE TRIGGER member_retirements_no_delete BEFORE DELETE ON member_retirements BEGIN SELECT RAISE(ABORT,'retirement history is permanent'); END;
