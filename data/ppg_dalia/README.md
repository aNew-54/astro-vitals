# PPG-DaLiA · actividad durante el uso de sensores de muñeca

La tabla permite entrenar un modelo experimental que reconozca ocho actividades del protocolo terrestre. Cada fila corresponde a un participante durante ocho segundos completos de una sola actividad. Los segmentos consecutivos no se solapan. La frecuencia cardíaca de referencia procede del ECG de pecho y cubre los mismos ocho segundos. En este conjunto se puede estudiar, por ejemplo, cómo cambia la señal de muñeca al subir escaleras o montar en bicicleta.

## Archivos

- [Descargar el original de UCI](https://archive.ics.uci.edu/ml/machine-learning-databases/00495/data.zip) (2,86 GB). Su ubicación local es `data/ppg_dalia/data.zip`. [Manual de los autores](README_original.pdf) · [Recibo de adquisición](fuente.json).
- [Inventario por participante](inventario.csv) y [manifiesto de variables, clases y particiones](manifest.json).
- [Entrenamiento](ventanas_train.csv), [validación](ventanas_validation.csv) y [prueba reservada](ventanas_test.csv). Las particiones contienen nueve, tres y tres participantes, respectivamente.

## Preparación

Se usaron los canales sincronizados del archivo original de cada persona. La etiqueta es la actividad de referencia a 4 Hz. Se conservan los segmentos con una sola clase del protocolo, con muestras completas y finitas de acelerometría (32 Hz), señal óptica BVP (64 Hz), conductancia eléctrica de la piel y temperatura (4 Hz). Las seis variables de entrada son el promedio y la desviación poblacional de la magnitud de la aceleración, la desviación del BVP, el promedio y la desviación de la conductancia, y el promedio de temperatura. Conservan la escala numérica de los canales publicados.

El objetivo es `actividad`. Los valores posibles son reposo sentado, escaleras, fútbol de mesa, bicicleta, conducción, almuerzo, caminar y trabajo. Los códigos de transición quedan fuera. `fc_ecg_referencia_bpm` se conserva para comparación con la señal óptica y queda fuera de los predictores de actividad. También se excluyen de los predictores el participante, la partición y los tiempos de la ventana. Los límites temporales son segundos relativos, con inicio incluido y fin excluido.

La asignación de participantes se reproduce ordenando sus identificadores por SHA-256 con un prefijo fijo de la fuente. La descarga se comprueba frente al recibo antes de procesar los registros. Se ha usado Python 3.14 con NumPy 2.5.4 en un entorno dedicado a datos. Desde la raíz, ejecutar `.\.venv-datos\Scripts\python.exe ml\preparar_wearables.py ppg_dalia`.

**Atribución.** Reiss, A., Indlekofer, I. y Schmidt, P. (2019). *PPG-DaLiA*. UCI Machine Learning Repository. Las tablas del proyecto son transformaciones propias de los datos publicados con licencia CC BY 4.0. [Ficha y licencia](https://archive.ics.uci.edu/dataset/495/ppg+dalia) · [DOI](https://doi.org/10.24432/C53890)
