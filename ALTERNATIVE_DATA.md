# ASTRO-VITALS · data inventory by task

Review of **November 4, 2026**. Each link in the table leads to local data with provenance, units and reproduction instructions. Sizes correspond to the indicated preparation, not to independent observations. The [data and outputs contract](CONTRATO_DE_DATOS.md) defines which source each component may use.

| Task | Source available in the project | Use and scope |
| --- | --- | --- |
| 60 s HR forecast | [BIDMC](data/bidmc/README.md) · 3,170 windows from 52 usable records out of 53 inventoried | Real hospital HR and RR. Target observed in the same session. |
| Body and cabin classification | [Simulated fusion](data/fusion_simulada/README.md) · 9,470 windows from 30 profiles and 120 sessions | Four labeled patterns. Training, validation and test with separate profiles and seeds. |
| Activity and movement | [PPG-DaLiA](data/ppg_dalia/README.md) · 11,693 8 s windows, 15 participants | Eight study activities and a contemporaneous heart reference. Land-based extension. |
| Experimental stress | [WESAD](data/wesad/README.md) · 1,060 30 s windows, 15 participants | Baseline, induced stress or amusement condition. Non-commercial scientific use with attribution. |
| Rest | [MMASH](data/mmash/README.md) · 22 episodes from 21 participants with recorded sleep | Summary of duration, efficiency and awakenings. Coverage of a single day is limited for longitudinal prediction. |
| Historical ISS environment | [NASA EDA, RR-1](data/iss_rr1/README.md) · 12,087 cabin readings and 39 daily radiation records | Real series from the facility. CO₂ in ppm and absorbed dose rate in mGy/day. |
| Historical solar context | [NASA DONKI](data/donki/README.md) · one event selected from 12 records in the query | Date, instrument and identifier for the interface. The simulated dosimeter keeps its own provenance. |

Prototype 0.1 replays BIDMC 01 and its demo scenarios. The datasets in this table were prepared separately for training, evaluation or future integrations. To combine columns, a verifiable match of person or location, session, time and units is required. The real ISS series is kept at its original frequency, separate from the signals of the synthetic cohort.

**Reproduction.** From the root, run `.\.venv\Scripts\python.exe ml\descargar_fuentes.py` to obtain or verify PPG-DaLiA, WESAD, MMASH and DONKI. The activity and stress ZIPs total about 5.1 GB and are stored in the project. To produce their derivatives, a separate environment with NumPy is used. The guides linked above give the commands for each source. BIDMC, RR-1 and the synthetic cohort have their own preparers.

**Verified lightweight file.** [bidmc_01_Numerics.csv](https://physionet.org/files/bidmc/1.0.0/bidmc_csv/bidmc_01_Numerics.csv) takes up 7,644 bytes and contains 481 rows, from second 0 to 480. Only that file can be downloaded. The header includes spaces after the commas; the adapter must strip them when reading the names.

```csv
Time [s], HR, PULSE, RESP, SpO2
0,94,93,25,97
1,94,93,25,97
2,94,93,25,97
3,92,93,26,97
```

| Column | Interpretation |
| --- | --- |
| Time [s] | Relative time of the record, in seconds |
| HR | ECG-derived heart rate, beats/minute |
| PULSE | PPG-derived pulse, beats/minute |
| RESP | Respiratory rate from the monitor, breaths/minute |
| SpO2 | Peripheral oxygen saturation, % |

The record includes `NaN`, for example in PULSE and SpO2 between seconds 111 and 123: convert to `null`, without substituting zero. The full collection contains 53 eight-minute clinical records; the parameters are sampled at 1 Hz. They come from hospitalized patients, so replaying them demonstrates acquisition and visualization; it does not validate a diagnosis for astronauts. [BIDMC description](https://physionet.org/content/bidmc/1.0.0/).

**Proposed adapter rules.** Store `source_kind="replayed"`, the record name, URL and original time offset. The CSV only provides relative time: do not invent an original clinical date. Keep the current replay instant separate. When it ends, stop or start a new explicit session. If simulated CO₂ or radiation is added, each signal keeps its own provenance. Do not label that set as a synchronized real measurement.

**Attribution when distributing or presenting the data.** Include a visible notice: "Contains information from BIDMC PPG and Respiration Dataset v1.0.0, available under the Open Data Commons Attribution License v1.0", with links to the [source](https://physionet.org/content/bidmc/1.0.0/) and the [ODC-By 1.0 license](https://physionet.org/content/bidmc/view-license/1.0.0/). Also keep the notices of the [LICENSE file](https://physionet.org/files/bidmc/1.0.0/LICENSE) alongside any copy. Reference for the work: Pimentel et al., *Towards a Robust Estimation of Respiratory Rate from Pulse Oximeters*, [DOI 10.1109/TBME.2016.2613124](https://doi.org/10.1109/TBME.2016.2613124). The dataset page also offers the current PhysioNet reference.

When the challenge resources are received, population, permissions, units, frequency, identifiers and labels will be reviewed. A document can justify an environmental rule even if it provides no series for training. A physiological series can be incorporated into the forecast if it meets its contract, even if it lacks CO₂.
