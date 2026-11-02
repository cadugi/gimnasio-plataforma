import sqlite3
from pathlib import Path
import time
path=Path('/opt/topfitness/.local/whatsapp_queue.sqlite')
connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
try:
    print('Cola del VPS:',dict(connection.execute('SELECT state,COUNT(*) FROM jobs GROUP BY state')))
    print('Estados Meta:',dict(connection.execute('SELECT status,COUNT(*) FROM receipts GROUP BY status')))
    print('Respuestas del bot:',dict(connection.execute('SELECT state,COUNT(*) FROM outbound GROUP BY state')))
    print('Incidencias:',dict(connection.execute("SELECT error_code,COUNT(*) FROM jobs WHERE error_code!='' GROUP BY error_code")))
finally:connection.close()
