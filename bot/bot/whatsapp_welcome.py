"""Reservation landing response. No booking backend, Flows or personal links."""
import re
import unicodedata

RESERVATIONS_URL = 'https://whatsapp.gimnasio.example/reservas'
WELCOME_TEXT = 'Hola, te damos la bienvenida a TopFitness. Puedes consultar horarios y reservar tus clases desde nuestra web.'


def normalize(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', (text or '').casefold())
                   if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^\w\s/]', ' ', text).split())


class ReservationWelcome:
    reservation_landing = True
    cooldown = 300

    def __init__(self, store):
        self.store = store
        store.c.execute('''CREATE TABLE IF NOT EXISTS whatsapp_welcome_state(
            user TEXT PRIMARY KEY, last_message REAL NOT NULL, last_reply REAL NOT NULL)''')
        store.c.commit()

    def handle_inbound(self, user, stamp, text=None, token=None):
        now = self.store.clock()
        # Delayed webhooks must not start a conversation outside the service window.
        if not 0 <= now - stamp < 86400:
            return None
        row = self.store.c.execute(
            'SELECT last_message,last_reply FROM whatsapp_welcome_state WHERE user=?',
            (str(user),)).fetchone()
        if row and stamp < row[0]:
            return None
        clean = normalize(text)
        stopped = clean in ('baja', 'stop', 'parar avisos')
        greeting = bool(re.match(r'^(hola|buenas|buenos dias|buenas tardes|buenas noches|hey|hello)( |$)', clean))
        shortcut = clean in ('menu', 'inicio', 'empezar', '/start', 'reservar',
                             'reservas', 'reservar clase', 'reservar clases', 'web', 'horarios')
        first = row is None or stamp - row[0] >= 86400
        respond = (not stopped and (first or greeting or shortcut or bool(token))
                   and (row is None or now - row[1] >= self.cooldown))
        self.store.c.execute('''INSERT INTO whatsapp_welcome_state VALUES (?,?,?)
            ON CONFLICT(user) DO UPDATE SET last_message=excluded.last_message,
            last_reply=excluded.last_reply''',
            (str(user), stamp, now if respond else (row[1] if row else 0)))
        self.store.c.commit()
        if respond:
            return {'text': WELCOME_TEXT, 'whatsapp_reservations_cta': True}
        return None
