# Buscador único de socios · 23/10/2026

Disponible en **Centro de control → Buscar socios**, en la lupa superior y con **Ctrl/Cmd + K**.

1. Escribir al menos dos caracteres del nombre, teléfono o número y pulsar **Buscar**.
2. Elegir la ficha por nombre y teléfono. Los números repetidos se advierten; no se elige una persona automáticamente.
3. Consultar contacto, cuotas de Innux, contratos, domiciliaciones y reservas. También aparecen las últimas bajas y mantenimientos vinculados.
4. **Ver contrato** abre ese contrato; **Gestionar cuotas** abre ese socio. En móvil, **Volver a resultados** permite regresar a la selección.

## Comportamiento y límites

- Solo se reúnen automáticamente Altas e Innux cuando existe una referencia explícita a la misma ficha. Un nombre, teléfono o número coincidente no basta. Las personas que comparten teléfono permanecen separadas.
- Las reservas vinculadas se distinguen de las coincidencias por teléfono. Estas últimas muestran el nombre y un aviso de comprobación.
- **El conector actual del PC de Innux no busca por teléfono.** Los teléfonos se buscan en Altas y Reservas; para socios que solo existen en Innux hay que usar nombre o número. Ampliar este punto exige actualizar y verificar el conector del PC, cuyo código no está en este repositorio. La limitación aparece en pantalla.
- Si una fuente falla, se conservan los resultados de las otras y se indica qué no se pudo consultar. No se presenta una caída como ausencia de socios o de cuotas.
- Se respetan los permisos existentes: Reservas requiere owner; las domiciliaciones solo se entregan al administrador de Altas. No se amplían roles.
- La ficha limita contratos y domiciliaciones a los últimos 30 registros, reservas a 30 y bajas/mantenimientos a 10. Los módulos originales conservan la gestión completa.
- La consulta no crea, modifica ni vincula socios ni confirma cobros o reservas. Clientes se abre sin consultar o actualizar la jornada de caja. Durante la prueba se retiró exclusivamente un metadato de día vacío creado por la lectura antigua, tras comprobar que no tenía actividad.

## Verificación

- 78 pruebas de Caja y 17 de Centro/SSO/permisos superadas.
- 20 comprobaciones nuevas de Altas y 13 de Reservas/MySQL: tildes, teléfonos compartidos, referencias, entradas SQL, datos históricos y lectura sin escrituras. MySQL usó tablas temporales privadas de la conexión.
- 90 comprobaciones existentes de Altas/bajas, 11 de la entrega anterior y 11 de reglas de reservas superadas en bases aisladas.
- Cinco pruebas de interfaz con respuestas simuladas: fuentes caídas, respuestas antiguas, nombres escapados, fallos de Innux y navegación móvil.
- Navegación real con qa_total: búsqueda por teléfono y número, ficha con contrato y cuota, enlaces al contrato y a las cuotas, lista vacía y móvil de 390 × 844 sin desbordamiento. Sin errores JavaScript ni operaciones reales de cobro, firma o reserva.
- Acceso anónimo rechazado con 401, petición sin CSRF con 403 y selección alterada con 400. La auditoría conserva el nombre qa_total.
- Comparadas las 22 tablas de negocio de Altas/Caja con la copia previa: sin cambios. Reservas y horarios de ambas bases MySQL también coinciden.

## Publicación y recuperación

Rama: `codex/buscador-socios-20261023`. Sin PR.

Antes de editar, 288 ficheros compartidos desplegados coincidían con el repo. Copia completa del código, configuración, releases, tres SQLite y ambas bases MySQL: `/var/backups/topfitness-search/20261022T221117Z` (fecha del directorio en UTC).

Se conservaron los enlaces de releases y la copia antigua recovery. Se reinició Centro para cargar los cambios y Caja para aislar la consulta de socios; no se reiniciaron PHP, nginx ni WhatsApp. La retirada de qa_total conserva el buscador: manifiesto y originales sin la excepción QA actualizados y verificados por hash. No se ejecutó el borrado de esa cuenta, que sigue disponible.

La recuperación de código debe usar los ficheros afectados del respaldo; no restaurar bases completas sobre actividad posterior. No hay migraciones de esquema para este buscador.
