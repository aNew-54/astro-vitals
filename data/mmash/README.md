# MMASH · episodios de sueño

La [tabla de episodios](episodios_sueno.csv) permite reproducir un resumen de descanso en la interfaz. Hay 22 episodios de 21 participantes en las 22 carpetas del estudio. El archivo de `user_11` contiene solo la cabecera y `user_1` aporta dos episodios. La unidad de análisis es un intervalo observado. La cobertura de una jornada limita el estudio de tendencias personales de varias noches. [Inventario de cobertura](resumen.json)

| Campos | Interpretación |
| --- | --- |
| `subject_id`, `episode`, `source_member` | Participante, posición de la fila dentro de su archivo y ruta de origen dentro de `MMASH.zip`. |
| `bed_day`, `bed_time`, `onset_day`, `onset_time`, `out_day`, `out_time` | Días relativos y horas tal como se publicaron para la entrada en cama, el inicio del sueño y la salida de la cama. |
| `bed_min`, `sleep_min`, `latency_min`, `waso_min` | Minutos en cama, minutos de sueño, latencia y minutos despierto tras el inicio del sueño. |
| `efficiency_pct`, `awakenings` | Eficiencia publicada en porcentaje y número de despertares. |
| `same_day_midnight_wrap` | Vale 1 en los cuatro episodios cuyo reloj de salida es anterior al de entrada y que conservan el mismo día relativo en el original. Para presentar duraciones se usa `bed_min`. |

Para reproducir la tabla desde la raíz del proyecto, ejecutar `.\.venv\Scripts\python.exe ml\preparar_sueno.py`. El script verifica el SHA-256 del ZIP y de la licencia contra las [sumas publicadas](SHA256SUMS.txt). Lee las filas de `sleep.csv` en memoria, selecciona campos y conserva los valores de origen. Los demás archivos del ZIP, entre ellos actigrafía e intervalos entre latidos, permanecen disponibles para otras preguntas. [Comprobante de descarga](fuente.json)

Esta tabla deriva de *Multilevel Monitoring of Activity and Sleep in Healthy People* v1.0.0, de Rossi, Da Pozzo, Menicagli, Tremolanti, Priami, Sirbu, Clifton, Martini y Morelli (2020), PhysioNet. La base original y la tabla derivada se distribuyen bajo la Open Data Commons Open Database License v1.0. La muestra se recogió en adultos jóvenes sanos en Tierra. [DOI y atribución](https://doi.org/10.13026/cerq-fc86) · [Ficha y referencias de los autores](https://physionet.org/content/mmash/1.0.0/) · [Licencia](LICENSE.txt)
