# Efectivo, domiciliación y número oficial de socio

Actualización del 16/10/2026.

## Pagos

Las nuevas altas solo admiten efectivo o domiciliación bancaria. Tarjeta se ha eliminado del selector y se rechaza en el guardado, preparación y firma del contrato. La migración aditiva 004 incorpora un trigger para impedir nuevos contratos con otro método. Los PDF y contratos históricos firmados no se reescriben; las etiquetas de métodos históricos se conservan únicamente para leer correctamente documentos anteriores.

## Número de Innux

Se añadió al detalle del contrato el botón «Recuperar número de Innux», reservado a recepción y administración. Es una consulta de lectura, no crea fichas ni reserva números libres.

El lector busca como máximo dos coincidencias por documento normalizado y fecha de nacimiento, utilizando consultas parametrizadas sobre campos comprobados en la base instalada: NIF, DataNascimento, IDCliente y Numero. Después comprueba que ese número pertenece únicamente al IDCliente encontrado. Si falta la ficha o el número, hay varias coincidencias o falla la conexión, no vincula ni inventa nada. Una vinculación previa diferente requiere revisión. Las restricciones únicas y la transacción local evitan vincular el mismo número a dos fichas de esta aplicación.

Cuando se recupera correctamente se registra `VERIFIED_READ_ONLY`, el identificador interno de Innux y su número de socio. Este estado acredita la comprobación de lectura en ese momento; no afirma que se haya creado la cuenta, cargado la fotografía, activado cuotas o completado otros procesos de Innux. No modifica la instantánea ni el PDF ya firmados. La confirmación manual anterior continúa diferenciada.

La consulta está bloqueada en entornos demo/test para no buscar documentos ficticios en producción. También exige un contrato real firmado. Para preparar un entorno real autorizado, añadir a su configuración privada:

```json
{
  "innux_number_lookup": {
    "enabled": true,
    "python": "C:/Users/User/AppData/Local/Programs/CajaPython/python.exe"
  }
}
```

Ese ejecutable debe tener pyodbc y ejecutarse con una cuenta Windows autorizada para leer Innux. El servidor recibe únicamente documento y nacimiento por stdin; no se incluyen en argumentos de procesos ni logs. El helper utiliza la conexión integrada Windows existente a la instancia local TOPFITNESS y la base InnuxSports. No necesita una contraseña SQL en el proyecto. Verificar este mecanismo en otro equipo antes de habilitarlo. No se ha cambiado ninguna configuración a producción ni se ha probado la búsqueda contra una persona real.

## Por qué no asignamos un hueco libre

La revisión de metadatos comprobó que IDCliente es IDENTITY y tiene la clave primaria. Numero es otro campo y no aparece protegido por un índice único en el inventario accesible de dbo.Clientes. No se ha identificado un procedimiento oficial de reserva o creación de altas. Elegir un hueco o calcular MAX+1 fuera del procedimiento de Innux puede colisionar con una alta realizada simultáneamente desde recepción. No se insertan ni actualizan filas de Innux. El inventario de índices, sin filas de clientes, está en INNUX_NUMERACION_METADATA.json.

Flujo disponible: completar el alta en la aplicación oficial de Innux → consultar el número desde nuestro panel → recuperar y vincular el número encontrado. La creación automática con asignación oficial continúa pendiente de verificar el mecanismo compatible de alta. La nueva consulta se ha probado con conexiones simuladas y datos ficticios, no con un socio real.

## Validación

Pruebas aisladas de lector: coincidencia única, ausencia, documento duplicado, número duplicado, cambio de titular del número, número pendiente y entradas inválidas. Pruebas de aplicación: bloqueo de tarjeta y de consultas demo, permisos, vinculación sin modificar el contrato firmado, rechazo de identidad obsoleta y de doble vinculación. Prueba visual: únicamente dos opciones de pago. No se ejecutan escrituras ni controles de ventanas de Innux.
