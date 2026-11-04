# BIDMC · datos para el pronóstico de frecuencia cardíaca

Preparación v1 del 3 de noviembre de 2026. Se conservaron los parámetros numéricos y los metadatos de los 53 registros de BIDMC 1.0.0. Cada archivo original se comprobó con el listado SHA-256 del proveedor. La copia ligera del prototipo sigue siendo independiente. [Dataset y cita](https://physionet.org/content/bidmc/1.0.0/) · [Sumas publicadas](raw/SHA256SUMS.txt)

## Resultado

| Partición | Participantes asignados / con ventanas | Registros asignados / con ventanas | Ventanas utilizables |
| --- | --- | --- | --- |
| Entrenamiento | 32 / 31 | 39 / 38 | 2.316 |
| Validación | 7 / 7 | 7 / 7 | 427 |
| Prueba reservada | 7 / 7 | 7 / 7 | 427 |

Los 53 registros suman 25.493 mediciones y corresponden a 46 identificadores de participante. Tres identificadores se repiten en varios registros. La partición se fijó antes de crear ventanas usando el campo `MIMIC II matched wdb ID` de cada archivo `Fix.txt`. El participante del registro 01 pertenece a entrenamiento porque el equipo ya usó un ejemplo suyo para diseñar el contrato. Los demás se ordenan por el hash SHA-256 de un prefijo fijo y su identificador. Se asignan los últimos siete a prueba y los siete anteriores a validación. [Significado del identificador en PhysioNet](https://archive.physionet.org/physiobank/database/mimic2wdb/matched/)

De 3.232 ventanas candidatas, 61 se excluyeron por cobertura o antigüedad de señales y una por falta del objetivo a +60 s. Las 61 primeras pertenecen al registro 13, con FR válida en el 23,91 % de los segundos. El inventario conserva su causa de exclusión. El registro 23 empieza en −1 s y termina en 479 s. Se conservan los tiempos de origen. [Inventario por registro](preparado/inventario.csv)

## Archivos para el equipo de modelos

- Las [ventanas de entrenamiento](preparado/ventanas_train.csv), las [de validación](preparado/ventanas_validation.csv) y las [de prueba](preparado/ventanas_test.csv) se guardan por separado. Cada fila cuenta con identificador de registro y participante, instante de decisión, instante objetivo, 14 variables de entrada y `target_hr_bpm`.
- El [manifiesto](preparado/manifest.json) enumera las 14 columnas predictoras. Usar únicamente esa lista como entrada del modelo. Los identificadores y tiempos sirven para auditoría. La FC medida en `target_t_s` es la respuesta de entrenamiento.
- El [inventario](preparado/inventario.csv) registra cobertura de FC y FR, mayor hueco por canal, segundos ausentes, partición, sumas de verificación y ventanas excluidas por registro. Las mediciones y los metadatos originales se conservan en `raw/bidmc_csv/`.

**Preparación.** La cuadrícula es de 1 Hz. Se respeta el orden temporal original y se genera un ejemplo cada 5 s si caben los 120 s de historia y el instante objetivo en el mismo registro. Las ventanas incluyen `t` y excluyen `t − duración`. En cada ventana de 30 y 120 s se exige al menos 80 % de mediciones válidas por canal y una última lectura de hasta 5 s de antigüedad. Para este experimento se consideran FC positivas hasta 300 bpm y FR positivas hasta 100/min. Son filtros de ingeniería. Valores no finitos, huecos y mediciones excluidas se conservan en los originales y se omiten de los cálculos. Una FC objetivo ausente descarta esa fila.

Por señal se calcula el último valor válido, y en cada ventana, la media, la desviación estándar poblacional y la pendiente por mínimos cuadrados respecto al tiempo real en segundos. No hay interpolación. Las pendientes se expresan en bpm/s o (respiraciones/minuto)/s. Cada transformación termina en `t`. El desplazamiento entre `t` y `target_t_s` es siempre de 60 s.

**Referencia de validación.** En las mismas 427 ventanas de siete participantes, conservar la última FC dio un error absoluto medio de **2,31 bpm**. Extrapolar la pendiente de los últimos 30 s desde la última lectura válida hasta el instante objetivo dio **6,51 bpm**. Son errores medios por ventana en registros hospitalarios terrestres. Las ventanas vecinas se solapan. Se reservó la prueba para la evaluación final del método elegido.

## Reproducción

Desde la raíz del proyecto, con Python 3.10 o posterior y la biblioteca estándar, ejecutar lo siguiente en PowerShell. El primer comando comprueba los archivos locales y descarga de PhysioNet los que falten. El segundo reconstruye las tablas sin conexión.

```powershell
.\.venv\Scripts\python.exe ml\bidmc_source.py
.\.venv\Scripts\python.exe ml\preparar_bidmc.py
```

**Atribución.** Contiene información de BIDMC PPG and Respiration Dataset v1.0.0, de Pimentel, Johnson y Charlton (2018), distribuida bajo Open Data Commons Attribution License v1.0. Se proporciona el aviso original junto a los archivos y se identifican arriba las transformaciones propias. [DOI](https://doi.org/10.13026/C2208R) · [Licencia ODC-By](https://physionet.org/content/bidmc/view-license/1.0.0/) · [Aviso original](raw/LICENSE)
