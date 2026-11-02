-- Horas de descanso: de noche las ofertas retienen la plaza pero el aviso y el plazo empiezan al terminar la madrugada. Vacío = sin descanso.
INSERT IGNORE INTO tf_notify_settings(k,v) VALUES ('OFFERS_QUIET_FROM','23:00'),('OFFERS_QUIET_TO','08:00');
INSERT IGNORE INTO tf_migrations(name) VALUES ('005_offers_quiet');
