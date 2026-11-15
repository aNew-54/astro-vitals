# Cabin and Physiology Fusion Data

The synthetic v2 cohort contains **108,000 measurements at 1 Hz**. It consists of four 15-minute sessions for each of the 30 fictional profiles. Each session records HR in bpm, RR in breaths/min, CO₂ partial pressure in mmHg, activity phase, and the second at which the phase begins. Its purpose is to train and evaluate the recognition of the four patterns defined by the simulator. [Model Contract](../../CONTRATO_DE_DATOS.md) · [Reference Scenarios](../../scenarios/README.md)

| Partition | Profiles | Sessions | Rest | Normal Activity or Recovery | Recovery Deviation | Cabin and Physiology Change | Usable Windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Training | 20 | 80 | 3,409 | 1,822 | 476 | 599 | 6,306 |
| Validation | 5 | 20 | 895 | 421 | 130 | 124 | 1,570 |
| Held-out Test | 5 | 20 | 905 | 421 | 128 | 140 | 1,594 |

## Model Usage

Use the ordered `features` list and the `pattern` target from the manifest. Person and session identifiers, along with relative time, are used to track each row. Each complete person is assigned to a single partition before sessions and windows are generated. Each session receives its own seed derived from the partition, profile, and scenario. [Manifest](manifest.json) · [Training](ventanas_train.csv) · [Validation](ventanas_validation.csv) · [Test](ventanas_test.csv)

Every 5 seconds, measurements up to that point are summarized. For each channel, the latest valid value, mean, population standard deviation, and slope per second are calculated over 30-second and 120-second windows. At least 80% of valid samples are required in each window and channel, with the latest reading no more than 5 seconds old. The phase, its duration, and the differences in HR and RR relative to calibration complete the 25 features. Calibration is the mean of each signal during the first 120 seconds of rest in that session, rounded to five decimal places. [Telemetry with Per-Row Provenance](telemetria.csv.gz)

## Generation and Labels

- The profile defines baseline HR, RR, and CO₂ levels within the ranges of 60–85 bpm, 11–18 breaths/min, and 1.5–3.0 mmHg, respectively. These are simulation parameters. The effort level in each session increases the target HR by 28–64 bpm and the target RR by 6–13 breaths/min. Signals gradually approach their targets with a time constant of 24–46 seconds. Oscillation and noise are added before measurements are recorded.

- During slow recovery, the time constant increases by a factor of 3–5. During a cabin intervention, CO₂ targets increase by 1.4–3.4 mmHg, RR by 4–8 breaths/min, and HR by 1–8 bpm. Each session retains, in its audit records, the difference compared with normal progression under the same profile and effort level.

- In the normal scenarios, internal boundaries are shifted by up to 18 seconds. In the cabin scenario, the intervention start time is distributed between approximately 140 and 590 seconds within each partition. This provides ordinary rest and rest with intervention periods of comparable duration. Each session also introduces a 3–15-second interruption in one channel starting after second 180. The cabin scenario additionally includes an RR data loss lasting 43–56 seconds during the episode.

- The latent label is activated after 30 seconds of an isolated intervention. For training, a 120-second window with a single phase and class, sufficient measurements, and a persistent change relative to the control is required. During recovery, differences of at least 2 bpm and 0.5 breaths/min are required. During cabin interventions, at least 0.5 mmHg and 1 breath/min are required. Overlapping interventions, weak changes, and transitions are identified for episode-level evaluation.

There are 21,600 annotated time points in total. Of these, 9,470 are candidate windows, 2,880 correspond to calibration, 6,650 to transitions, 1,152 to insufficient signal, 1,444 to overlapping patterns, and 4 to weak contrast. Seeds, scenarios, and differences relative to the control remain available in audit files. [Sessions](sesiones.csv) · [Annotations](anotaciones.csv.gz)

## Replay and Verification

From the project root, using the project's Python interpreter and its standard library:

```powershell
.\.venv\Scripts\python.exe -B ml\preparar_fusion.py
.\.venv\Scripts\python.exe -B -m unittest discover -s ml -p test_fusion.py
```

The tests reconstruct each window's values from its telemetry, verify consistency with the annotations, and check the separation of profiles, sessions, and seeds. In this cohort, **every cabin-change window has at least one ordinary-rest window with an identical phase duration within its own partition**. This match was verified for all 599, 124, and 140 cabin windows, respectively.

Subsequent training must report results by class and profile, since rest is more frequent and neighboring windows overlap. The generalization that can be measured here corresponds to new profiles from this simulator.