# Pendientes concretos (nada de esto está dado por terminado)

## Integración con Innux (bloquea cobros reales)
- El PC del mostrador NO está vinculado: falta `agent.py pair` con el token (en el VPS: `/home/ubuntu/caja-token-dispositivo.txt`, 600). Hasta entonces no hay prueba real de `health`, búsqueda, `clients.get` ni `cash.day`.
- Los campos de `clients.get`/`clients.history` que usa la pantalla «4 · Cuotas» (IDCartao, PlanDescripcion, IDPlanoPagamento, ValidadeInicio/Fim, signature…) están tomados del contrato; no se han visto con datos reales.
- Cobros web desactivados (`payments_enabled=false`). Activarlos solo tras el corte (docs/CORTE.md).
- Arranque del puente antes de login (tarea S4U) y reinicio real: trabajo del PC, sin verificar.

## Histórico y corte
- El importador está probado con datos sintéticos; falta una vista previa con la exportación real (`agent.py export`).
- Los XLSX históricos (octubre, A1=2002 €, cinco propuestas del 13/10) no se han importado: hacen falta los libros.
- Base actual = piloto con usuario `admin` (contraseña inicial en `/home/ubuntu/caja-admin-inicial.txt`, obliga a cambiarla). En el corte se crea base nueva y se copian usuarios/dispositivo (`copy-identity`).

## Operación
- Copias solo en el mismo VPS (`/var/backups/topfitness-caja`). Falta copia externa y un ensayo de recuperación en instancia aislada.
- Reintento automático del informe mensual tras fallo: se registra el error (`reports`) pero no hay reintento programado; se regenera al exportar o al cerrar otro día.
- Poda de copias antiguas no implementada.
- Gestión de usuarios solo por CLI (sin pantalla).
- Sin búsqueda en caché cuando el PC está apagado (la búsqueda exige consulta real; el pago siempre la exige).
- Servidor sin HEAD; sin límite de tasa propio para el puente (lo limita nginx por tamaño; el token es de 48 bytes).

## Pruebas
- 41 pruebas automáticas (lógica, protocolo y HTTP real en bucle local). La interfaz solo tiene comprobación de sintaxis JS: no se ha recorrido a mano en navegador ni en móvil/tablet.
