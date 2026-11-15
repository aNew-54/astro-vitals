# WESAD · Laboratory-Induced Stress Conditions

The table makes it possible to study differences between the baseline, induced stress, and amusement conditions of the WESAD protocol in terrestrial participants. The label describes the condition scheduled by the experiment during the measurement. The tables are intended for research and non-commercial use, in accordance with the authors' terms.

## Files

- [Download the original dataset from the authors](https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx/download) (2.25 GB). Its local location is `data/wesad/WESAD.zip`. [Authors' manual](README_original.pdf) · [Acquisition receipt](fuente.json).
- [Participant inventory](inventario.csv) and [manifest of variables, classes, and splits](manifest.json).
- [Training set](ventanas_train.csv), [validation set](ventanas_validation.csv), and [held-out test set](ventanas_test.csv). The splits contain nine, three, and three participants, respectively.

## Data Preparation

Consecutive 30-second non-overlapping segments were generated using the synchronized wrist data and study annotations at 700 Hz. Only windows entirely labeled as baseline (1), stress (2), or amusement (3) are included. Transitions, meditation, annotations outside these three conditions, and signals containing missing or non-finite samples are excluded.

The input signals are triaxial acceleration at 32 Hz, optical BVP signal at 64 Hz, and electrodermal activity and temperature at 4 Hz. Six features are calculated using the scales of the published sensor data: the mean and population standard deviation of acceleration magnitude, BVP standard deviation, the mean and standard deviation of electrodermal activity, and mean temperature. `condicion` indicates the condition to be recognized. Participant ID, data split, timestamps, and condition are excluded from the predictors.

Times are expressed in seconds from the beginning of the synchronized recording. Participant assignment can be reproduced by sorting their identifiers using SHA-256 with a fixed source prefix. Python 3.14 with NumPy 2.5.4 was used in a dedicated data environment. From the project root directory, run `.\\.venv-datos\Scripts\python.exe ml\preparar_wearables.py wesad`.

**Attribution.** Schmidt, P., Reiss, A., Duerichen, R., Marberger, C., and Van Laerhoven, K. (2018). *Introducing WESAD, a Multimodal Dataset for Wearable Stress and Affect Detection*. ICMI 2018. The derived tables retain the attribution and non-commercial scientific scope of the source. [Original terms and conditions](https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html) · [Publication](https://doi.org/10.1145/3242969.3242985)