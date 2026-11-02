CREATE TABLE tablet_invitations (
 id TEXT PRIMARY KEY,
 code_hash TEXT NOT NULL UNIQUE,
 issuer_id TEXT NOT NULL REFERENCES users(id),
 payload_enc TEXT NOT NULL,
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 used_at TEXT
);
CREATE INDEX tablet_invitation_expiry ON tablet_invitations(expires_at);
