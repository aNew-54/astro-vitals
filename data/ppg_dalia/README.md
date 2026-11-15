# PPG-DaLiA · Activity During Wrist-Worn Sensor Use

The table can be used to train an experimental model that recognizes eight activities from the terrestrial protocol. Each row corresponds to one participant performing a single activity for a complete eight-second period. Consecutive segments do not overlap. The reference heart rate is obtained from chest ECG and covers the same eight seconds. This dataset can be used to study, for example, how the wrist signal changes when climbing stairs or riding a bicycle.

## Files

- [Download the original dataset from UCI](https://archive.ics.uci.edu/ml/machine-learning-databases/00495/data.zip) (2.86 GB). Its local location is `data/ppg_dalia/data.zip`. [Authors' manual](README_original.pdf) · [Acquisition receipt](fuente.json).
- [Participant inventory](inventario.csv) and [manifest of variables, classes, and splits](manifest.json).
- [Training set](ventanas_train.csv), [validation set](ventanas_validation.csv), and [held-out test set](ventanas_test.csv). The splits contain nine, three, and three participants, respectively.

## Data Preparation

The synchronized channels from each participant's original file were used. The label is the reference activity sampled at 4 Hz. Segments are retained only when they contain a single protocol activity, with complete and finite samples from the accelerometer (32 Hz), optical BVP signal (64 Hz), electrodermal activity, and temperature (4 Hz). The six input features are the mean and population standard deviation of acceleration magnitude, BVP standard deviation, the mean and standard deviation of electrodermal activity, and mean temperature. They preserve the numerical scale of the published channels.

The target variable is `actividad`. Its possible values are sitting, stairs, table soccer, cycling, driving, lunch, walking, and working. Transition codes are excluded. `fc_ecg_referencia_bpm` is retained for comparison with the optical signal and is excluded from the activity predictors. Participant ID, data split, and window timestamps are also excluded from the predictors. Time boundaries are relative seconds, with the start included and the end excluded.

Participant assignment can be reproduced by sorting their identifiers using SHA-256 with a fixed source prefix. The download is verified against the receipt before processing the records. Python 3.14 with NumPy 2.5.4 was used in a dedicated data environment. From the project root directory, run `.\\.venv-datos\Scripts\python.exe ml\preparar_wearables.py ppg_dalia`.

**Attribution.** Reiss, A., Indlekofer, I., and Schmidt, P. (2019). *PPG-DaLiA*. UCI Machine Learning Repository. The project tables are custom transformations of the published data, distributed under the CC BY 4.0 license. [Dataset information and license](https://archive.ics.uci.edu/dataset/495/ppg+dalia) · [DOI](https://doi.org/10.24432/C53890)