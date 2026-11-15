# ASTRO-VITALS · MVP data and outputs contract

Design decision of November 3, 2026. This contract defines what the data, simulation and interface teams share. The [architecture](ARQUITECTURA_TECNICA.md) describes how to implement it and the [prototype 0.1 guide](prototype/README.md) describes what can already be run.

The product question is "how are my signals evolving during this activity, and which changes should I review?". On board, the heart rate forecast, the scenario pattern and the environmental state are computed separately. Each component communicates its availability and the evidence that supports it.

## Inputs

| Variable | Definition and unit | Who uses it |
| --- | --- | --- |
| Heart rate (HR) | Beats/minute (bpm). In BIDMC use `HR`, derived from the ECG. `PULSE` is a different optical measurement. | Required for both models. Visible in the console. |
| Respiratory rate (RR) | Breaths/minute. In BIDMC use `RESP`. | Required for both models. Visible in the console. |
| Activity | `rest`, `exercise`, `recovery` or `unknown`. Record the known phase and when it was communicated. | The classifier requires a known phase. The interface may show "unknown". |
| Time in activity | Seconds from the known start of the phase to the analysis instant. | Required for the classifier. If the start is missing, the duration is absent. |
| Personal HR and RR references | Values in the units of each signal, computed over a previous valid rest segment of the same person or retrieved from an identified earlier calibration. They are kept fixed during the episode. | The classifier uses differences with respect to these references. Without calibration, the interface shows "calibrating". |
| Cabin CO₂ | Partial pressure in mmHg of the module occupied at that moment. Convert from ppm only when the total pressure is also known. | Required for the four-pattern classifier. Environmental rules may evaluate this channel separately. |
| SpO₂ | Peripheral oxygen saturation in %. Optional field for display when the source allows it. | The column exists in the BIDMC CSV. Its on-screen integration is left for a later stage. |
| Dose rate | Local dosimeter reading in μSv/h, simulated in the demo. Keep the type of quantity and the source unit. | The environmental module integrates dose in μSv over valid intervals and records its coverage. |
| Self-report | Perceived exertion, discomfort and observations with time and author. | The interface associates it with the episode for human review. |

Each measurement keeps session, person or location as appropriate, measurement time, unit, source, quality and reception time. If the record only carries relative seconds, that offset is kept alongside the replay clock. A missing value is represented as `null`. Identities, scenario names and seeds serve for traceability, partitioning or evaluation and are left out of the predictor variables.

## What each model learns

A row represents a window of **one person in one session**, with end instant `t`. The engineering proposal computes one row every 5 s using the previous 120 s, including `t`. For each required signal, the last value is obtained and the mean, dispersion and slope are computed over 30 s and 120 s windows. Only data known on board at the time the analysis is issued are used. Each model's manifest will fix the numeric definition and the order of its columns.

| Component | Inputs when issuing the analysis | Target during training | Output in the interface |
| --- | --- | --- | --- |
| Basic forecast | HR and RR of that window. It may work on BIDMC even if the activity is unknown. | Valid HR observed in the **same session** at `t + 60 s`. Examples without that observation are excluded. | Estimate in bpm, target instant and method. |
| Experimental classifier | HR, RR, local CO₂, known phase, duration and HR/RR differences with respect to the personal reference. | Pattern labeled for that window of the synthetic scenario. | Simulated pattern, observations, duration of the change and next review step. |

The classifier's four labels are `baseline_expected` (expected rest), `activity_expected` (expected activity or recovery), `persistent_recovery_deviation` (persistent deviation during recovery) and `combined_cabin_physiology_pattern` (joint cabin and physiology change). Labels are stored apart from the telemetry the model receives. The rest reference alone is insufficient to label a recovery as deviated. The generator must specify which recovery it expects for that activity and which deviation persists.

**Verifiable example.** At second 120 of BIDMC record 01, HR is 92 bpm and RR is 22/min. To prepare a forecast row we use only the history up to that second. The training response is the HR at second 180, **91 bpm**. The persistence reference would have forecast **92 bpm**. This record lacks the activity and cabin context required by the classifier. [CSV included in the project](prototype/data/bidmc_01_Numerics.csv)

## What the system computes and what the interface shows

| Output | Responsible | Expected behavior |
| --- | --- | --- |
| Availability per component | Quality rules | Indicate whether the result is evaluable, calibrating, missing history/signal, has stale data or lacks the model. Keep the reason and the instant of the last analysis. |
| Evidence of the change | On-board engine | Show observed values, trends, duration and the reference used. A class is presented with its simulated origin. |
| Cabin and radiation state | Environmental rules | Show local CO₂, rate and accumulated dose with coverage. A historical DONKI event provides date and external context. Personal exposure is computed from the dosimeter. |
| Review message | Episode templates | Explain which signal to review and allow recording an observation or acknowledging the alert. The acknowledgment is stored separately from the condition's state. |

Each model evaluates **its own required inputs**. The initial design criteria require at least 80 % valid samples per required channel in the window and a maximum age of 5 s for its last valid reading. They will be tuned in validation. With insufficient data, the affected model's output is left without a value. If a current HR is available, the interface may show the persistence reference separately with its method. A classifier abstention is shown with its reason, separate from the four classes.

## Data and evaluation

- **Forecast.** Start with the BIDMC numeric records. Split people before creating windows, keeping each complete record in a single partition. If the source only allows splitting records, document that limitation. Compare the mean absolute error in bpm against persistence and trend extrapolation on the same windows. Choose the method with validation and report its performance on the held-out test set.
- **Classification.** Generate sessions coherent with synchronized physiology, activity and environment. Separate profiles and seeds between training, validation and test. Measure macro-F1, confusions, abstentions, false alerts per simulated hour and delay per episode. The results describe those scenarios.
- **Other sources.** PPG-DaLiA and WESAD provide land-based windows split by person. MMASH provides sleep episodes and DONKI a historical solar event. RR-1 provides cabin series in ppm and ambient radiation in mGy/day. These sources are used with their own labels, units and clocks. [Inventory and usage criteria](DATOS_ALTERNATIVOS.md)

As of November 4 there are 3,170 real forecast windows split by participant and 9,470 synthetic classifier windows split by profile. The telemetry, the annotations and the explicit list of predictors are kept. [Forecast](data/bidmc/README.md) · [Classification](data/fusion_simulada/README.md)

## Pending decisions

| When | What remains to be defined | What allows closing it |
| --- | --- | --- |
| Before connecting live sources | Late-arrival policy and admissible offset between body and cabin. BIDMC processing by record time is already defined. | Replay out-of-order data and verify what information the node knew at each analysis. |
| Before training the classifier | Set which errors and delays are acceptable for the demonstration and which cases must produce abstention. | Review the scenarios and acceptance criteria before using the test partition. |
| Before integrating on-board calibration | In the cohort, the mean of the first 120 s of valid rest per session is used. The validity period and recovery of a reference between real sessions remain to be defined. | Share the transformations between training and inference and check when "calibrating" should be shown. |
| Before choosing a model for the demo | Acceptance criteria for the classifier and its alerts, including tolerance to false alerts and to delay. | Set criteria before opening the held-out test. Tune abstention with validation. Keep the best-performing forecast method identified. |
| Before integrating the interface | Self-report scale, opening/closing/acknowledgment of episodes, review text and presentation when only some components are evaluable. | Review a complete episode with the team, and the health terms with a mentor. |
| When reviewing the resources announced for November 13 | Accessible files, units, permissions, population, labels and usefulness for each component. The DONKI event and the RR-1 reference series are already available. | Record which resource changes an input, a rule or a screen and which provides context only. |

The scope implemented today is that of **version 0.1**. It replays HR and RR from a BIDMC record, simulates activity and environment, applies rules and shows the last pulse as a 60 s reference. Training, personal calibration, self-report, on-disk persistence and the link with Earth correspond to the planned MVP.
