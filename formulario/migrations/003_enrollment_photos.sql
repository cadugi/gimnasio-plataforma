CREATE TABLE draft_photos (
 draft_id TEXT PRIMARY KEY REFERENCES drafts(id) ON DELETE CASCADE,
 image_enc TEXT NOT NULL, image_hash TEXT NOT NULL,
 width INTEGER NOT NULL CHECK(width BETWEEN 160 AND 1280),
 height INTEGER NOT NULL CHECK(height BETWEEN 160 AND 1280),
 created_at TEXT NOT NULL
);
CREATE TABLE contract_photos (
 contract_id TEXT PRIMARY KEY REFERENCES contracts(id),
 image_enc TEXT NOT NULL, image_hash TEXT NOT NULL,
 width INTEGER NOT NULL, height INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER contract_photo_immutable_update BEFORE UPDATE ON contract_photos
 BEGIN SELECT RAISE(ABORT,'Signed photo is immutable'); END;
CREATE TRIGGER contract_photo_immutable_delete BEFORE DELETE ON contract_photos
 BEGIN SELECT RAISE(ABORT,'Signed photo is immutable'); END;
