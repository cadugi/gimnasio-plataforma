CREATE TABLE innux_devices (
 id TEXT PRIMARY KEY,
 secret_enc TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 last_seen TEXT,
 catalog_enc TEXT,
 created_at TEXT NOT NULL
);
CREATE TABLE innux_nonces (
 device_id TEXT NOT NULL REFERENCES innux_devices(id),
 nonce TEXT NOT NULL,
 expires INTEGER NOT NULL,
 PRIMARY KEY(device_id,nonce)
);
CREATE TABLE innux_sequence (
 id INTEGER PRIMARY KEY CHECK(id=1),
 next_number INTEGER NOT NULL CHECK(next_number>=6325)
);
INSERT INTO innux_sequence(id,next_number) VALUES(1,6325);
CREATE TABLE innux_jobs (
 id TEXT PRIMARY KEY,
 contract_id TEXT NOT NULL UNIQUE REFERENCES contracts(id),
 member_id TEXT NOT NULL UNIQUE REFERENCES members(id),
 number INTEGER UNIQUE CHECK(number>=6325),
 device_id TEXT REFERENCES innux_devices(id),
 state TEXT NOT NULL CHECK(state IN ('QUEUED','RUNNING','REVIEW_REQUIRED','COMPLETED','CANCELLED')),
 options_enc TEXT NOT NULL,
 result_enc TEXT,
 lease_until INTEGER,
 error_code TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX innux_jobs_queue ON innux_jobs(state,created_at);
