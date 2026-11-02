# Corte a producción (hay un único sistema autoridad por día)

Estado actual: **piloto**. Cobros web desactivados (`payments_enabled=false`). El escritorio sigue siendo la autoridad
de manuales y cierres. El puente cambia cuotas en Innux pero NO sincroniza manuales/gastos/cierres entre SQLite y VPS.
Usar las dos cajas a la vez para el mismo día duplicaría cobros o perdería matrículas.

1. Congelar: acordar fecha y hora; en el escritorio no editar los días transferidos desde ese momento.
2. En el PC: `python agent.py export --output RUTA_PRIVADA_NUEVA.json` (con Caja cerrada o sin movimientos). Transferir por canal privado (no Git, no web).
3. En el VPS: parar `topfitness-caja`; renombrar la base piloto (`caja.sqlite3` → `caja-piloto-<fecha>.sqlite3`).
4. Base nueva en versión 1: `python3 -m caja.cli migrate --upto 1`.
5. Vista previa: `python3 -m caja.cli import export.json` (en memoria: cuentas, reconciliación de cierres, advertencias).
6. Importar: `python3 -m caja.cli import export.json --commit` (transaccional, idempotente por hash, conserva UUID, timestamps, ids de cierres/auditoría).
7. Activar protecciones: `python3 -m caja.cli migrate` (versión 2: triggers). Nunca desactivarlos en producción.
8. Recuperar identidad: `python3 -m caja.cli copy-identity /var/lib/topfitness-caja/caja-piloto-<fecha>.sqlite3` (usuarios y hash del dispositivo; no hay contraseñas ni tokens en claro).
9. Arrancar el servicio, comprobar totales de 3 días por muestreo contra el escritorio, comprobar `health`/búsqueda en la pantalla de estado.
10. Un administrador activa «Permitir cobros de cuota desde la web» (Más opciones → Precios y configuración) y se bloquea definitivamente la edición en el escritorio.
11. Primer cobro real: con una ficha y un importe acordados por la dirección. La autorización histórica de una ficha de pruebas no autoriza cobros ficticios.

**Rollback del corte:** parar el servicio, reactivar el escritorio. Los movimientos creados en la web tras el corte
no existen en el escritorio: exportar antes (Excel día/mes) y reintroducirlos o mantener la web como autoridad. No se pierde nada de la base web.

El Excel histórico (octubre u otros) no está en el SQLite: hay que aportar los XLSX/informes para trasladar esas filas.
