CREATE TABLE innux_searches (
 id TEXT PRIMARY KEY,
 actor TEXT NOT NULL,
 query_enc TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('QUEUED','RUNNING','DONE','FAILED')),
 result_enc TEXT,
 error_code TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX innux_searches_queue ON innux_searches(state,created_at);
