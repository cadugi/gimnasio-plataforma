# Caja web Top Fitness — https://whatsapp.gimnasio.example/alta/caja/

Aplicación propia (Python 3.12 estándar, SQLite WAL/synchronous FULL), independiente del portal de altas.
Sin dependencias externas: el XLSX se genera/lee con `zipfile`.

| Pieza | Dónde |
|---|---|
| Código | `/opt/topfitness-caja/releases/<UTC>` y enlace `current` |
| Servicio | `topfitness-caja.service` (usuario `topfitness-caja`, socket `/run/topfitness-caja/app.sock`, sin red) |
| Datos | `/var/lib/topfitness-caja/caja.sqlite3` (700) · informes en `exports/` |
| Copias | `/var/backups/topfitness-caja` (diaria, antes/después de cada cierre y reapertura, antes de migrar) |
| Nginx | `snippets/topfitness-caja.conf` incluido UNA vez en el server 443 (`location ^~ /alta/caja/`) |
| Copia previa al despliegue | `/var/backups/topfitness-caja-predeploy` (nginx, snippets, units, estado HTTP antes/después) |

## Módulos (`caja/`)
`money` céntimos enteros y regla de efectivo · `ledger` movimientos, conciliación, exclusiones, cierres versionados ·
`bridge` protocolo 1 (`/bridge/v1/poll` y `/result`), cola duradera y efectos contables · `service` cobros con caja
y administración de cuotas · `auth` personal, roles, sesiones · `reports`/`xlsx` informes · `importer` histórico ·
`cli` administración · `server` HTTP.

## Roles (backend)
consulta (ver) · caja (+registrar) · responsable (+cerrar, cuotas, exportar) · admin (+reabrir, borrar cuotas, config, usuarios).

## Administración
```
python3 -m caja.cli create-user NOMBRE --name "Nombre" --role responsable   # contraseña por consola
python3 -m caja.cli provision-device --token-out /ruta/privada               # token del puente (solo se guarda su hash)
python3 -m caja.cli revoke-device
python3 -m caja.cli backup | check | migrate
```
Ejecutar como `sudo -u topfitness-caja env CAJA_DATA=/var/lib/topfitness-caja python3 -m caja.cli ...` desde `current`.

## Garantías
- Auditoría y cierres: triggers que abortan UPDATE/DELETE; movimientos no se borran; un día cerrado rechaza altas/cambios de movimientos.
  Un administrador con acceso a la base o al disco del VPS podría saltarse estas garantías: no se anuncia inmunidad frente a infraestructura.
- Cobros: el manual y la solicitud/job nacen en la MISMA transacción con el mismo UUID. Nada suma hasta `succeeded` verificado.
  `retry` conserva UUID y datos; solo `rejected` + `PAYMENT_REJECTED` anula; `review_required` bloquea el cierre hasta resolución humana auditada.
- Cierre: bloquea con pagos pendientes/en revisión, recalcula en servidor, guarda snapshot inmutable, versión por día, copia antes y después.
- Tests: `python3 -W ignore -m unittest discover -s tests` (41 pruebas, datos sintéticos, adaptador falso; sin SQL real).
