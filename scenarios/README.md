# Experimental Classifier v1 Script

Four fictional 15-minute sessions make it possible to review the expected label for each window before generating training signals. Times are relative to the beginning of each session, and intervals include the start and exclude the end. [Interval-based script](guion_v1.csv) · [Annotations every 5 seconds](anotaciones_v1.csv)

| Session | Events in the Script | What Should Be Distinguishable |
| --- | --- | --- |
| Baseline | Initial rest, exercise starting at 240 s, recovery starting at 480 s, and rest starting at 720 s. | Exercise and normal recovery share `activity_expected`. Rest is labeled `baseline_expected`. |
| Recovery | Exercise starts at 200 s. From 420 s onward, a slower recovery than the expected curve for that profile and effort is introduced. | From 450 s onward, `persistent_recovery_deviation`. The first complete candidate window ends at 570 s. |
| Cabin | While at rest, local CO₂ and respiratory response increase together from 240 s to 630 s. RR data is unavailable between 570 s and 630 s. | The `combined_cabin_physiology_pattern` begins at 270 s. A sensor interruption preserves the ground truth of the script while limiting evaluation. |
| Coincidence | After exercise, slow recovery and a cabin change are introduced simultaneously between 420 s and 660 s. | This is an ambiguous case for a single-label classifier. It is retained to evaluate behavior when multiple patterns occur together. |

**Demo Annotation Rules.** The first 120 seconds of each session are used for resting calibration. An isolated intervention is considered sustained after 30 uninterrupted seconds. Changing sensor availability does not reset the intervention. In baseline sessions, the label is determined by the phase. In intervention sessions, the label is determined by the injected change and its duration. These are experimental decisions specific to the synthetic script.

`pattern_at_t` stores the scenario ground truth at the end of the window. `window_status` indicates whether the window can be used as a single-class example. A candidate window spans 120 seconds with the same phase and label. Mixed windows are retained as transitions. When interventions coincide, the single label is left empty. Scheduled sensor outages are evaluated using the same coverage and data freshness requirements defined in the contract. If a window meets multiple exclusion conditions, they are recorded in the following order: calibration, pattern coincidence, insufficient signal, and transition.

The script generates **720 time points**, of which **313** are candidates before telemetry generation. They are distributed as follows: 160 rest, 92 expected activity/recovery, 24 recovery deviations, and 37 cabin changes. The 233 transition time points can also be used to measure detection delay from the beginning of an episode. Additionally, 96 calibration points, 30 insufficient-signal points, and 48 coincidence points are retained.

**Script Application.** The v2 fusion cohort extends these templates with 30 profiles, variable intervention timings, and rest controls of equal duration. Its splits contain the generated measurements and undergo additional quality and contrast filters. The counts above refer exclusively to the four script templates. [Classifier training data](../data/fusion_simulada/README.md) · [Input and output contract](../CONTRATO_DE_DATOS.md)

The annotations can be reproduced from the project root directory using the following command:

```powershell
.\\.venv\Scripts\python.exe ml\preparar_etiquetas.py
```