-- Avisos push y ofertas de lista de espera. Aditiva e idempotente: solo CREATE ... IF NOT EXISTS.
-- No modifica tablas existentes. Los interruptores nacen APAGADOS.
CREATE TABLE IF NOT EXISTS tf_migrations (
  name varchar(100) NOT NULL PRIMARY KEY,
  applied_at timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tf_notify_settings (
  k varchar(50) NOT NULL PRIMARY KEY,
  v varchar(200) NOT NULL,
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT IGNORE INTO tf_notify_settings(k,v) VALUES ('PUSH_SEND_ENABLED','0'),('OFFERS_ENABLED','0');

-- Móvil asociado a una persona. La cookie guarda un secreto aleatorio; aquí solo su SHA-256.
-- Autoriza únicamente funciones de reservas de esa persona.
CREATE TABLE IF NOT EXISTS tf_devices (
  id bigint unsigned NOT NULL AUTO_INCREMENT PRIMARY KEY,
  person_id bigint unsigned NOT NULL,
  token_hash char(64) NOT NULL,
  label varchar(60) NOT NULL DEFAULT '',
  platform varchar(20) NOT NULL DEFAULT '',
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  last_seen_at timestamp NULL DEFAULT NULL,
  revoked_at timestamp NULL DEFAULT NULL,
  revoked_by varchar(100) DEFAULT NULL,
  UNIQUE KEY uq_device_token (token_hash),
  KEY ix_device_person (person_id,revoked_at),
  CONSTRAINT fk_device_person FOREIGN KEY (person_id) REFERENCES tf_people(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tf_push_subscriptions (
  id bigint unsigned NOT NULL AUTO_INCREMENT PRIMARY KEY,
  device_id bigint unsigned NOT NULL,
  endpoint_hash char(64) NOT NULL,
  endpoint text NOT NULL,
  p256dh varchar(200) NOT NULL,
  auth_secret varchar(100) NOT NULL,
  status enum('ACTIVE','EXPIRED','REVOKED','FAILED') NOT NULL DEFAULT 'ACTIVE',
  test_sent_at timestamp NULL DEFAULT NULL,
  test_confirmed_at timestamp NULL DEFAULT NULL,
  failure_count int NOT NULL DEFAULT 0,
  last_error varchar(100) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  UNIQUE KEY uq_sub_endpoint (endpoint_hash),
  KEY ix_sub_device (device_id,status),
  CONSTRAINT fk_sub_device FOREIGN KEY (device_id) REFERENCES tf_devices(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Oferta temporal de una plaza. La entrada de espera sigue en inscripciones_cola mientras está PENDING.
-- pending_key permite una única oferta pendiente por entrada de espera.
CREATE TABLE IF NOT EXISTS tf_offers (
  id bigint unsigned NOT NULL AUTO_INCREMENT PRIMARY KEY,
  wait_id int NOT NULL,
  booking_id bigint unsigned DEFAULT NULL,
  person_id bigint unsigned NOT NULL,
  horario_id int NOT NULL,
  fecha date NOT NULL,
  token_hash char(64) NOT NULL,
  status enum('PENDING','ACCEPTED','DECLINED','EXPIRED','CANCELLED','FAILED') NOT NULL DEFAULT 'PENDING',
  created_at datetime NOT NULL DEFAULT current_timestamp(),
  expires_at datetime NOT NULL,
  resolved_at datetime DEFAULT NULL,
  resolved_by varchar(100) DEFAULT NULL,
  reservation_id int DEFAULT NULL,
  pending_key tinyint AS (IF(status='PENDING',1,NULL)) PERSISTENT,
  UNIQUE KEY uq_offer_token (token_hash),
  UNIQUE KEY uq_offer_pending_wait (wait_id,pending_key),
  KEY ix_offer_session (horario_id,fecha,status),
  KEY ix_offer_expiry (status,expires_at),
  KEY ix_offer_person (person_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Evento de negocio, escrito en la misma transacción que el cambio.
CREATE TABLE IF NOT EXISTS tf_notify_events (
  id bigint unsigned NOT NULL AUTO_INCREMENT PRIMARY KEY,
  kind enum('REMINDER','OFFER','OFFER_ACCEPTED','CLASS_CANCELLED','SCHEDULE_CHANGED','RECEPTION_BOOKING','TEST') NOT NULL,
  person_id bigint unsigned NOT NULL,
  booking_id bigint unsigned DEFAULT NULL,
  offer_id bigint unsigned DEFAULT NULL,
  horario_id int DEFAULT NULL,
  fecha date DEFAULT NULL,
  dedupe_key varchar(120) NOT NULL,
  not_before datetime NOT NULL DEFAULT current_timestamp(),
  ttl_at datetime NOT NULL,
  status enum('PENDING','DONE','SKIPPED','EXPIRED','FAILED') NOT NULL DEFAULT 'PENDING',
  created_at datetime NOT NULL DEFAULT current_timestamp(),
  UNIQUE KEY uq_event_dedupe (dedupe_key),
  KEY ix_event_due (status,not_before),
  KEY ix_event_offer (offer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Un envío por suscripción. accepted_at = aceptado por el servicio push; opened_at = confirmación explícita de la persona.
CREATE TABLE IF NOT EXISTS tf_push_outbox (
  id bigint unsigned NOT NULL AUTO_INCREMENT PRIMARY KEY,
  event_id bigint unsigned NOT NULL,
  subscription_id bigint unsigned NOT NULL,
  status enum('PENDING','SENDING','ACCEPTED','FAILED','EXPIRED','SKIPPED') NOT NULL DEFAULT 'PENDING',
  attempts int NOT NULL DEFAULT 0,
  next_attempt_at datetime NOT NULL DEFAULT current_timestamp(),
  accepted_at datetime DEFAULT NULL,
  opened_at datetime DEFAULT NULL,
  last_error varchar(100) DEFAULT NULL,
  created_at datetime NOT NULL DEFAULT current_timestamp(),
  UNIQUE KEY uq_outbox (event_id,subscription_id),
  KEY ix_outbox_due (status,next_attempt_at),
  CONSTRAINT fk_outbox_event FOREIGN KEY (event_id) REFERENCES tf_notify_events(id),
  CONSTRAINT fk_outbox_sub FOREIGN KEY (subscription_id) REFERENCES tf_push_subscriptions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Auditoría mínima. Sin teléfonos completos ni tokens.
CREATE TABLE IF NOT EXISTS tf_notify_audit (
  id bigint unsigned NOT NULL AUTO_INCREMENT PRIMARY KEY,
  actor varchar(100) NOT NULL,
  action varchar(50) NOT NULL,
  person_id bigint unsigned DEFAULT NULL,
  device_id bigint unsigned DEFAULT NULL,
  detail_json text NOT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  KEY ix_audit_action (action,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Límite de intentos (identificación, oferta, prueba). bucket = hash de IP/dispositivo + acción.
CREATE TABLE IF NOT EXISTS tf_rate_limits (
  bucket char(64) NOT NULL,
  window_start int unsigned NOT NULL,
  hits int unsigned NOT NULL DEFAULT 1,
  PRIMARY KEY (bucket,window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO tf_migrations(name) VALUES ('001_push_offers');
