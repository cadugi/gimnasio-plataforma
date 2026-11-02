-- Envío real de correos con el contrato. Aditiva: no borra ni reescribe datos.
-- PROVIDER_REQUIRED sigue siendo válido para los registros históricos.
ALTER TABLE email_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE email_jobs ADD COLUMN next_try_at TEXT;
ALTER TABLE email_jobs ADD COLUMN sent_at TEXT;
ALTER TABLE email_jobs ADD COLUMN last_error TEXT;
CREATE INDEX email_jobs_state ON email_jobs(state,next_try_at);
CREATE INDEX email_jobs_contract ON email_jobs(contract_id,created_at);
