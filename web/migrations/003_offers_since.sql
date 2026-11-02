-- Fecha de activación de las ofertas. Las esperas creadas ANTES de esta fecha conservan el comportamiento anterior hasta terminar su sesión.
-- Se rellena al activar OFFERS_ENABLED (procedimiento de activación); vacío = modo nuevo desactivado.
INSERT IGNORE INTO tf_notify_settings(k,v) VALUES ('OFFERS_SINCE','');
INSERT IGNORE INTO tf_migrations(name) VALUES ('003_offers_since');
