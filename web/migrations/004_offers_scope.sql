-- Acota las ofertas a ciertos horarios (ids separados por comas). Vacío = todos. Sirve para probar con una clase de prueba sin afectar a las reales.
INSERT IGNORE INTO tf_notify_settings(k,v) VALUES ('OFFERS_ONLY_HORARIOS',''),('TEST_HORARIO','');
INSERT IGNORE INTO tf_migrations(name) VALUES ('004_offers_scope');
