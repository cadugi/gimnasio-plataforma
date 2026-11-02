# Copias de seguridad y recuperación

Este documento describe qué se copia, dónde se guarda, qué falta y cómo restaurar el servicio si el VPS falla.

> **Estado a 22-oct-2026:** las copias locales funcionan. La copia **externa** (`topfitness-offsite`) está preparada pero **desactivada**: no existe `/etc/topfitness-offsite/` ni la clave pública ni el destino. Hasta que se configure, si el VPS se pierde, se pierden también sus copias.

## 1. Qué hay hoy

| Dato | Dónde está | Quién lo copia | Frecuencia | Sale del VPS |
|---|---|---|---|---|
| Altas (`contracts.sqlite`) | `/var/backups/topfitness-altas-daily/` | `topfitness-altas-backup.timer` | Varias veces al día | No |
| Caja (`caja.sqlite3`) | `/var/backups/topfitness-caja/` | Caja (copia diaria propia) | Diaria | No |
| Centro de administración (`cuentas.sqlite`) | `/var/backups/` | `topfitness-cuentas-backup.timer` | Diaria | No |
| Reservas (MariaDB `topfitness_reservas`) | `/var/backups/` | `topfitness-backup.timer` | Diaria | No |
| Código y configuración | Repo el repositorio privado de producción | Manual, por commit | Al cambiar | **Sí** (GitHub) |
| Credenciales de systemd | `/etc/credstore.encrypted/`, `/var/lib/systemd/credential.secret` | — | — | No |
| Copia externa cifrada | `topfitness-offsite` | Script preparado | Diaria (cuando se active) | Sería sí |

## 2. Lo que NO está en ninguna copia

- **Fotos de socios y ficheros subidos** (`003_enrollment_photos`): ruta de almacenamiento por confirmar.
- **PDFs de contratos firmados** y **calendarios** del bot.
- **Colas y estados de WhatsApp** (`whatsapp_queue.sqlite`, `whatsapp_state.sqlite`).
- **Copias de seguridad guardadas solo en el propio VPS**: si el disco falla, se pierden.

Antes de dar el sistema por recuperable hay que decidir dónde viven estos datos y añadirlos al paquete externo.

## 3. Activar la copia externa

El script `/usr/local/sbin/topfitness-offsite-backup` genera un paquete cifrado con GPG **para la clave pública de la propiedad**. Así, quien sube el paquete no puede leerlo y solo la clave privada (guardada fuera del VPS) lo abre.

Hace falta:

1. `/etc/topfitness-offsite/recipient.pub.asc`: clave pública GPG de la propiedad (`gpg --armor --export`).
2. `/etc/topfitness-offsite/offsite.conf` con `DEST="usuario@host:/ruta/"` (destino por rsync sobre SSH) y, si aplica, `SSH_KEY`.

Después:

```bash
sudo /usr/local/sbin/topfitness-offsite-backup --dry-run   # genera y verifica el paquete, no sube nada
sudo systemctl enable --now topfitness-offsite.timer       # solo cuando el dry-run sea correcto
```

## 4. Procedimiento de restauración

Se hace en un VPS nuevo (Ubuntu 24.04), nunca sobre producción sin copia previa.

1. **Obtener el paquete** del destino externo y comprobar su SHA-256 contra el fichero `.sha256` que lo acompaña.
2. **Descifrar** con la clave privada de la propiedad (`gpg --decrypt`). Sin esa clave el paquete no se puede abrir.
3. **Verificar contenido:** `sha256sum -c SHA256SUMS` dentro del paquete.
4. **Restaurar claves** (`claves/`): `credential.secret` y `credstore.encrypted/` a sus rutas. Sin ellas los datos de Altas no se pueden leer. `altas-keys.json` va en claro dentro del paquete cifrado: bórralo del disco tras usarlo.
5. **Restaurar bases de datos:**
   - MariaDB: `gunzip -c reservas.sql.gz | mariadb topfitness_reservas`
   - SQLite: descomprimir `caja.sqlite3.gz` y `cuentas.sqlite.gz` en sus rutas y comprobar `PRAGMA integrity_check;`
   - Altas: `altas-contracts.sqlite.gz` a la ruta de `contracts.sqlite`.
6. **Restaurar código** desde el repo al commit correspondiente a la fecha de la copia: `formulario/`, `caja/`, `centro-administracion/`, `web/`, `bot/` y `sistema/` (nginx y systemd).
7. **Arrancar servicios** (`topfitness-altas`, `topfitness-caja`, `topfitness-cuentas`, `topfitness-whatsapp`, timers) y revisar `journalctl`.
8. **Comprobar:** el healthcheck debe pasar; acceso al formulario y a la caja; prueba de alta en un entorno de prueba, nunca con socios reales.

## 5. Control de errores

- `topfitness-healthcheck.timer` está activo. Hay que confirmar que **avisa a alguien** cuando falla; hoy no está verificado.
- El repo guarda el historial: si un cambio rompe algo, se vuelve al commit anterior y se redespliega.
- **Prueba de restauración:** una vez al mes, restaurar la última copia en un entorno de prueba y anotar el resultado y el tiempo que tardó.

## 6. Pendiente

- [ ] Aportar la clave pública GPG de la propiedad.
- [ ] Aportar el destino de la copia externa (`DEST`).
- [ ] Decidir dónde viven las fotos y los PDFs y añadirlos al paquete.
- [ ] Guardar la clave privada GPG y las credenciales fuera del VPS (gestor de contraseñas).
- [ ] Activar `topfitness-offsite.timer` tras el dry-run.
- [ ] Primera prueba de restauración completa.
