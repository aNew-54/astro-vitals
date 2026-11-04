# WESAD · condiciones de estrés inducido en laboratorio

La tabla permite estudiar diferencias entre las condiciones basal, estrés inducido y diversión del protocolo WESAD en participantes terrestres. La etiqueta describe la condición que el experimento programó durante la medición. Las tablas son para investigación y uso no comercial según las condiciones de los autores.

## Archivos

- [Descargar el original de los autores](https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx/download) (2,25 GB). Su ubicación local es `data/wesad/WESAD.zip`. [Manual de los autores](README_original.pdf) · [Recibo de adquisición](fuente.json).
- [Inventario por participante](inventario.csv) y [manifiesto de variables, clases y particiones](manifest.json).
- [Entrenamiento](ventanas_train.csv), [validación](ventanas_validation.csv) y [prueba reservada](ventanas_test.csv). Las particiones contienen nueve, tres y tres participantes, respectivamente.

## Preparación

Se generaron segmentos consecutivos de 30 segundos sin solapamiento, usando la muñeca sincronizada y las anotaciones del estudio a 700 Hz. Se incluyen ventanas íntegramente etiquetadas como basal (1), estrés (2) o diversión (3). Se excluyen transiciones, meditación, anotaciones fuera de esas tres condiciones y señales con muestras ausentes o no finitas.

Las señales de entrada son aceleración triaxial a 32 Hz, señal óptica BVP a 64 Hz, y conductancia eléctrica de la piel y temperatura a 4 Hz. Se calculan seis variables en las escalas de los sensores publicados. Son el promedio y la desviación poblacional de la magnitud de la aceleración, la desviación del BVP, el promedio y la desviación de la conductancia, y el promedio de temperatura. `condicion` indica la condición que se intenta reconocer. Participante, partición, tiempos y condición quedan fuera de los predictores.

Los tiempos son segundos desde el comienzo del registro sincronizado. La asignación de participantes se reproduce ordenando sus identificadores por SHA-256 con un prefijo fijo de la fuente. Se ha usado Python 3.14 con NumPy 2.5.4 en un entorno dedicado a datos. Desde la raíz, ejecutar `.\.venv-datos\Scripts\python.exe ml\preparar_wearables.py wesad`.

**Atribución.** Schmidt, P., Reiss, A., Duerichen, R., Marberger, C. y Van Laerhoven, K. (2018). *Introducing WESAD, a Multimodal Dataset for Wearable Stress and Affect Detection*. ICMI 2018. Las tablas derivadas conservan la atribución y el alcance científico no comercial de la fuente. [Condiciones originales](https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html) · [Publicación](https://doi.org/10.1145/3242969.3242985)
