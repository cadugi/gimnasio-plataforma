# Condiciones facilitadas el 16/10/2026

La fuente es la fotografía del reverso del contrato aportada por el responsable del gimnasio en esta conversación. Se transcriben sus condiciones en `fixtures/condiciones_generales_20261016.txt` y su cláusula sexta en `fixtures/privacidad_impreso_20261016.txt`. Se han normalizado saltos de línea. No se ha sustituido el texto por un contrato inventado ni se han transcrito los identificadores fiscales poco legibles del pie.

La frase de la sección cuarta que sigue a «La resolución del contrato» necesita cotejo con una foto de mayor resolución o el documento original; está señalada en el texto. La transcripción también requiere cotejar las erratas y puntuación de «Salas y clases» antes de aprobarse.

La cláusula sexta cita la LO 15/1999 y presupone comunicaciones comerciales salvo oposición. Debe revisarse frente al marco vigente. El formulario mantiene su consentimiento comercial independiente y desmarcado. La sección cuarta menciona tarjeta bancaria; esto no habilita pagos con tarjeta, excluidos por decisión del centro. Se debe revisar la coherencia de las condiciones con el pago en efectivo admitido por el formulario.

La autorización bancaria del anverso se conserva. No se presenta como un mandato SEPA revisado; siguen pendientes los datos del acreedor y la validación del mandato.

La primera versión `IMPRESO-20261016-PENDIENTE-REVISION` incorpora el texto recibido. Posteriormente el responsable autorizó expresamente utilizar la cláusula de privacidad tal como aparece en su impreso. La versión `IMPRESO-20261016-PRIVACIDAD-AUTORIZADA` registra esa decisión en su referencia de aprobación y muestra la cláusula original sin el aviso de aprobación pendiente de privacidad. No se registra como revisión jurídica. Sigue pendiente exclusivamente el cotejo de la frase contractual ilegible para la aprobación del conjunto; los requisitos operativos de domiciliación se conservan. Los contratos ya firmados conservan su copia de condiciones y PDF. Los borradores deben revisar y aceptar la nueva versión si tenían seleccionada otra.

Importación: `scripts/import_supplied_terms.php`, exclusivamente por consola, sobre el almacenamiento separado del módulo de altas. Genera primero copia cifrada, no sustituye versiones aprobadas y es idempotente. No consulta ni escribe la base de reservas o Innux.

Referencias para la revisión: https://www.aepd.es/preguntas-frecuentes/2-tus-obligaciones-como-responsable-del-tratamiento/2-aplicacion-de-la-normativa/FAQ-0201-cual-es-la-normativa-vigente-en-proteccion-de-datos y https://boe.es/eli/es/lo/2018/12/05/3/con

## Cotejo con fotografía ampliada

El responsable ha aportado una segunda foto legible. La frase literal es: «La resolución del contrato no es exime en ningún caso el TITULAR, de la obligación de abonar las cuotas devengadas que tuviese pendientes de pago.» Se conserva la errata del impreso, sin corregirla silenciosamente. También se coteja «domiciliación bancaria de la cuota o tarjeta bancaria».

La versión IMPRESO-20261016-COTEJADO sustituye las pendientes mediante una nueva entrada inmutable. Su uso se autoriza operativamente con la instrucción expresa previa del responsable de utilizar sus hojas actuales y la aportación del fragmento solicitado. No es certificación jurídica. Importación explícita: scripts/import_supplied_terms.php --authorize-supplied-terms. La privacidad deja de bloquear; no se omiten validaciones de IBAN, consentimiento ni configuración de acreedor SEPA. Los textos anteriores y los contratos firmados se conservan.
