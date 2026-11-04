# ASTRO-VITALS · inventario de datos por tarea

Revisión del **4 de noviembre de 2026**. Cada enlace de la tabla lleva a datos locales con procedencia, unidades e instrucciones de reproducción. Los tamaños corresponden a la preparación indicada, no a observaciones independientes. El [contrato de datos y salidas](CONTRATO_DE_DATOS.md) define qué fuente puede usar cada componente.

| Tarea | Fuente disponible en el proyecto | Uso y alcance |
| --- | --- | --- |
| Pronóstico de FC a 60 s | [BIDMC](data/bidmc/README.md) · 3.170 ventanas de 52 registros utilizables de 53 inventariados | FC y FR hospitalarias reales. Objetivo observado en la misma sesión. |
| Clasificación de cuerpo y cabina | [Fusión simulada](data/fusion_simulada/README.md) · 9.470 ventanas de 30 perfiles y 120 sesiones | Cuatro patrones etiquetados. Entrenamiento, validación y prueba con perfiles y semillas separados. |
| Actividad y movimiento | [PPG-DaLiA](data/ppg_dalia/README.md) · 11.693 ventanas de 8 s, 15 participantes | Ocho actividades del estudio y referencia cardíaca contemporánea. Extensión terrestre. |
| Estrés experimental | [WESAD](data/wesad/README.md) · 1.060 ventanas de 30 s, 15 participantes | Condición basal, estrés inducido o diversión. Uso científico no comercial con atribución. |
| Descanso | [MMASH](data/mmash/README.md) · 22 episodios de 21 participantes con sueño registrado | Resumen de duración, eficiencia y despertares. La cobertura de una jornada es limitada para predicción longitudinal. |
| Entorno histórico de la ISS | [NASA EDA, RR-1](data/iss_rr1/README.md) · 12.087 lecturas de cabina y 39 registros diarios de radiación | Series reales de la instalación. CO₂ en ppm y tasa de dosis absorbida en mGy/día. |
| Contexto solar histórico | [NASA DONKI](data/donki/README.md) · un evento seleccionado entre 12 registros de la consulta | Fecha, instrumento e identificador para la interfaz. El dosímetro simulado conserva su propia procedencia. |

El prototipo 0.1 reproduce BIDMC 01 y sus escenarios de demo. Los conjuntos de esta tabla se prepararon por separado para entrenamiento, evaluación o futuras integraciones. Para combinar columnas se exige correspondencia verificable de persona o ubicación, sesión, tiempo y unidades. La serie real de la ISS se conserva en su frecuencia original, separada de las señales de la cohorte sintética.

**Reproducción.** Desde la raíz, ejecutar `.\.venv\Scripts\python.exe ml\descargar_fuentes.py` para obtener o verificar PPG-DaLiA, WESAD, MMASH y DONKI. Los ZIP de actividad y estrés suman unos 5,1 GB y se guardan en el proyecto. Para producir sus derivados se usa un entorno separado con NumPy. Las guías enlazadas arriba dan los comandos de cada fuente. BIDMC, RR-1 y la cohorte sintética tienen preparadores propios.

**Archivo ligero verificado.** [bidmc_01_Numerics.csv](https://physionet.org/files/bidmc/1.0.0/bidmc_csv/bidmc_01_Numerics.csv) ocupa 7.644 bytes y contiene 481 filas, del segundo 0 al 480. Se puede descargar únicamente ese archivo. La cabecera incluye espacios tras las comas; el adaptador debe eliminarlos al leer los nombres.

```csv
Time [s], HR, PULSE, RESP, SpO2
0,94,93,25,97
1,94,93,25,97
2,94,93,25,97
3,92,93,26,97
```

| Columna | Interpretación |
| --- | --- |
| Time [s] | Tiempo relativo del registro, en segundos |
| HR | Frecuencia cardíaca derivada del ECG, latidos/minuto |
| PULSE | Pulso derivado de PPG, latidos/minuto |
| RESP | Frecuencia respiratoria del monitor, respiraciones/minuto |
| SpO2 | Saturación periférica de oxígeno, % |

El registro incluye `NaN`, por ejemplo en PULSE y SpO2 entre los segundos 111 y 123: convertir a `null`, sin sustituir por cero. La colección completa contiene 53 registros clínicos de ocho minutos; los parámetros se muestrean a 1 Hz. Proceden de pacientes hospitalizados, por lo que su reproducción demuestra adquisición y visualización; no valida un diagnóstico para astronautas. [Descripción de BIDMC](https://physionet.org/content/bidmc/1.0.0/).

**Reglas del adaptador propuestas.** Guardar `source_kind="replayed"`, nombre del registro, URL y desplazamiento temporal original. El CSV solo ofrece tiempo relativo: no inventar una fecha clínica original. Mantener aparte el instante actual de reproducción. Al terminar, detener o iniciar una nueva sesión explícita. Si se añaden CO₂ o radiación simulados, cada señal conserva su propia procedencia. No etiquetar ese conjunto como una medición real sincronizada.

**Atribución al distribuir o presentar los datos.** Incluir un aviso visible: «Contiene información de BIDMC PPG and Respiration Dataset v1.0.0, disponible bajo Open Data Commons Attribution License v1.0», con enlaces a la [fuente](https://physionet.org/content/bidmc/1.0.0/) y la [licencia ODC-By 1.0](https://physionet.org/content/bidmc/view-license/1.0.0/). Conservar también los avisos del [archivo LICENSE](https://physionet.org/files/bidmc/1.0.0/LICENSE) junto a cualquier copia. Referencia del trabajo: Pimentel et al., *Towards a Robust Estimation of Respiratory Rate from Pulse Oximeters*, [DOI 10.1109/TBME.2016.2613124](https://doi.org/10.1109/TBME.2016.2613124). La ficha del dataset ofrece además la referencia actual de PhysioNet.

Al recibir los recursos del reto se revisarán población, permisos, unidades, frecuencia, identificadores y etiquetas. Un documento puede justificar una regla ambiental aunque no aporte series para entrenamiento. Una serie fisiológica puede incorporarse al pronóstico si cumple su contrato, aunque carezca de CO₂.
