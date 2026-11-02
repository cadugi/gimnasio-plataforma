# Adaptación al impreso facilitado por el centro

Referencia: fotografía del formulario Top Fitness / Top Fighters facilitada el 16/10/2026. La fotografía original no se copia al paquete ni se reutiliza el número de socio que aparece en ella. Las pruebas y los ejemplos siguen siendo ficticios.

| Campo del papel | Aplicación |
| --- | --- |
| N.º socio | Referencia oficial de Innux cuando ya está verificada; pendiente en un alta nueva. Nunca se inventa ni se permite editar desde la tablet |
| Fecha | Se obtiene del servidor, presentada como día-mes-año |
| Nombre y apellidos | Separados, en la misma fila y orden que en el impreso |
| Fecha de nacimiento y DNI/NIF/Pasaporte | Fecha y documento tipado, con validación diferenciada de DNI, NIE y pasaporte |
| Dirección y población | Misma disposición; código postal opcional como dato adicional |
| Teléfono 1, teléfono 2 y E-mail | Teléfono secundario opcional; el resto conserva su validación |
| Información comercial | Autorización positiva, independiente y desmarcada; no se copia la casilla negativa “No deseo” como aceptación implícita |
| Tarifas socio / tipo de contrato | Catálogo administrable; cuota, matrícula y total congelados al firmar |
| Mensual 39,90 € y matrícula 24,90 € | Coinciden con el ejemplo Fitness del catálogo. El total inicial es 64,80 € sin descuento. No se fijan en el código ni se validan otras tarifas por esta fotografía |
| Forma de pago | Se conserva domiciliación; efectivo y registro de tarjeta siguen disponibles como se solicitó inicialmente |
| Titular: el mismo / otro | Nombre y apellidos separados cuando es diferente. La cuenta no queda autorizada por la sola firma de otro socio |
| IBAN, entidad, sucursal, DC, número de cuenta | Se introduce y valida un IBAN completo. El desglose español se calcula para mostrarlo y para el PDF, sin almacenar columnas bancarias duplicadas |
| Autorización bancaria | Transcripción visible de la fotografía, con nota de cotejo pendiente. Se crea una versión legal provisional; no se declara aprobado el mandato SEPA |
| Por el Titular / Por el Centro | Firma del titular del contrato y espacio del centro en la primera página; la aceptación del centro continúa siendo auditada, vinculada al hash y sin reescribir el PDF |

La primera página del PDF reproduce esta estructura de campos y sus bloques, con cabecera Top Fitness / Top Fighters y datos de contacto visibles en el impreso. Condiciones, privacidad y detalles SEPA completos van en un anexo dentro del mismo PDF para mantener legibilidad. La firma dibujada no se anuncia como cualificada.

El archivo de referencia configurable es fixtures/paper_reference.json. Sus datos se copian al snapshot cifrado en el momento de revisar y firmar; cambios futuros en la referencia no alteran un contrato anterior. El número Innux también se congela con el valor conocido en ese momento. Una asignación posterior no reescribe el PDF antiguo.

scripts/apply_paper_reference.php prepara la versión provisional en la demo, de forma idempotente. No funciona en producción ni sustituye una versión activa que ya figure aprobada. No modifica PDFs firmados ni datos de socios. Una instalación nueva incorpora esta referencia desde setup.

No se han creado tablas nuevas: la plantilla y los campos de titular se guardan en los payloads cifrados ya previstos. La compatibilidad con titulares anteriores guardados como nombre completo se mantiene. Quedan pendientes la normativa a la que remite el papel y los textos completos de privacidad/SEPA para su revisión por el responsable.
