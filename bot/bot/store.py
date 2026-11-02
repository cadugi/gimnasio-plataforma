"""Estado persistente del adaptador; no guarda mensajes entrantes completos."""
import json
import secrets
import sqlite3
import time


class Store:
    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.c = sqlite3.connect(path)
        self.c.executescript('''
        CREATE TABLE IF NOT EXISTS selections(user TEXT PRIMARY KEY, person INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS buttons(token TEXT PRIMARY KEY, user TEXT NOT NULL, person INTEGER,
          payload TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS updates(id INTEGER PRIMARY KEY,user TEXT NOT NULL,reply TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')

    def selected(self, user):
        row = self.c.execute('SELECT person FROM selections WHERE user=?', (str(user),)).fetchone()
        return row[0] if row else None

    def select(self, user, person):
        self.c.execute('INSERT INTO selections VALUES (?,?) ON CONFLICT(user) DO UPDATE SET person=excluded.person', (str(user), person))
        self.c.commit()

    def button(self, user, person, action):
        token = secrets.token_urlsafe(18)
        self.c.execute('INSERT INTO buttons VALUES (?,?,?,?,?)', (token, str(user), person, json.dumps(action), self.clock()+900))
        self.c.commit()
        return token

    def get_button(self, token, user):
        row = self.c.execute('SELECT person,payload,expires FROM buttons WHERE token=? AND user=?', (token, str(user))).fetchone()
        if not row or row[2] < self.clock():
            return None
        return row[0], json.loads(row[1])

    def reply(self, update):
        row = self.c.execute('SELECT reply,sent FROM updates WHERE id=?', (update,)).fetchone()
        return (json.loads(row[0]), bool(row[1])) if row else None

    def save_reply(self, update, user, reply):
        self.c.execute('INSERT OR IGNORE INTO updates(id,user,reply) VALUES (?,?,?)', (update, str(user), json.dumps(reply)))
        self.c.commit()

    def sent(self, update):
        self.c.execute('UPDATE updates SET sent=1 WHERE id=?', (update,))
        self.c.execute("INSERT INTO metadata VALUES ('offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(update+1),))
        self.c.commit()

    def offset(self):
        row = self.c.execute("SELECT value FROM metadata WHERE key='offset'").fetchone()
        return int(row[0]) if row else 0
