-- Enlace opaco de la oferta, necesario hasta enviar el aviso (se borra al enviar o caducar), y lista de personas de prueba.
ALTER TABLE tf_notify_events ADD COLUMN IF NOT EXISTS link_token varchar(64) DEFAULT NULL;
ALTER TABLE tf_push_outbox ADD COLUMN IF NOT EXISTS http_status smallint DEFAULT NULL;
-- Con el interruptor general apagado, solo se envía a estas personas (ids de tf_people separados por comas). Vacío = nadie.
INSERT IGNORE INTO tf_notify_settings(k,v) VALUES ('PUSH_ALLOW_PERSONS','');
INSERT IGNORE INTO tf_migrations(name) VALUES ('002_push_link_allow');
