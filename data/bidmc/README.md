## BIDMC · Data for Heart Rate Forecasting

Preparation v1, November 3, 2026. The numeric parameters and metadata of the 53 BIDMC 1.0.0 records were preserved. Each original file was checked against the vendor’s SHA-256 listing. The prototype’s lightweight copy remains independent. Dataset and citation · Published checksums

## Result
Split	Participants assigned / with windows	Records assigned / with windows	Usable windows
Training	32 / 31	39 / 38	2,316
Validation	7 / 7	7 / 7	427
Held-out test	7 / 7	7 / 7	427

The 53 records total 25,493 measurements and correspond to 46 participant identifiers. Three identifiers appear in more than one record. The split was fixed before creating windows, using the MIMIC II matched wdb ID field of each Fix.txt file. The participant of record 01 belongs to training because the team already used one of their examples to design the contract. The rest are ordered by the SHA-256 hash of a fixed prefix plus their identifier. The last seven are assigned to test and the seven before them to validation. Meaning of the identifier at PhysioNet

Of 3,232 candidate windows, 61 were excluded for signal coverage or staleness and one for lack of the target at +60 s. The first 61 belong to record 13, which has valid RR in 23.91 % of seconds. The inventory keeps each exclusion’s cause. Record 23 starts at −1 s and ends at 479 s. Original timestamps are preserved. Per-record inventory

## Files for the modeling team
The training windows, the validation windows and the test windows are stored separately. Each row has record and participant identifiers, decision time, target time, 14 input features and target_hr_bpm.
The manifest lists the 14 predictor columns. Use only that list as model input. Identifiers and times are for auditing. The HR measured at target_t_s is the training response.
The inventory records HR and RR coverage, the longest gap per channel, missing seconds, split, checksums and windows excluded per record. The original measurements and metadata are kept in raw/bidmc_csv/.

Preparation. The grid is 1 Hz. The original temporal order is respected, and one example is generated every 5 s if the 120 s of history and the target time fit within the same record. Windows include t and exclude t − duration. In each 30 s and 120 s window, at least 80 % valid measurements per channel and a last reading no more than 5 s old are required. For this experiment, positive HR values up to 300 bpm and positive RR values up to 100/min are considered. These are engineering filters. Non-finite values, gaps and excluded measurements are kept in the originals and omitted from calculations. A missing target HR discards that row.

For each signal, the last valid value is computed, and for each window, the mean, the population standard deviation and the least-squares slope with respect to real time in seconds. There is no interpolation. Slopes are expressed in bpm/s or (breaths/minute)/s. Every transformation ends at t. The offset between t and target_t_s is always 60 s.

Validation baseline. On the same 427 windows from seven participants, keeping the last HR gave a mean absolute error of 2.31 bpm. Extrapolating the slope of the last 30 s from the last valid reading to the target time gave 6.51 bpm. These are per-window mean errors on land-based hospital recordings. Neighboring windows overlap. The test set was reserved for the final evaluation of the chosen method.

## Reproduction

From the project root, with Python 3.10 or later and the standard library, run the following in PowerShell. The first command checks the local files and downloads any missing ones from PhysioNet. The second rebuilds the tables offline.

powershell
.\.venv\Scripts\python.exe ml\bidmc_source.py
.\.venv\Scripts\python.exe ml\preparar_bidmc.py

Attribution. Contains information from the BIDMC PPG and Respiration Dataset v1.0.0, by Pimentel, Johnson and Charlton (2018), distributed under the Open Data Commons Attribution License v1.0. The original notice is provided alongside the files, and our own transformations are identified above. DOI · ODC-By License · Original notice