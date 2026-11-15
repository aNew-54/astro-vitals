Project proposal — NASA Space Apps 2026
==========================================

Historical exploration document of October 26. Mentions of October 28 reflect the calendar known at that time. The team now places the publication of the resources on November 13. To make implementation decisions, use the [current scope](MVP_ASTRO_VITALS.md) and the [data contract](CONTRATO_DE_DATOS.md).

Exploration document prepared on October 26, 2026. Team from Cajamarca, Peru, with general knowledge of software, data, design and electronics, without a health specialist. Number of members and effective hours pending. Working name: **Órbita — physiological recovery assistant**.

**Proposed decision.** Explore an application for an astronaut inside the habitat that answers: "Is my recovery after activity following my usual pattern?". Show sustained changes, their evidence and a next review step. The final scope depends on the full challenge statement and the available data.

The indexed official summary asks to gather health indicators and allow the astronaut to assess and act on their condition. I was able to consult that summary through search; opening the site directly returned a 502 error. The full statement and its detailed requirements have not yet been verified. [Official challenge](https://www.spaceappschallenge.org/2026/challenges/create-health-monitoring-software-for-astronauts-on-space-missions/).

The publication announced for October 28 corresponds to full statements and resources; it does not guarantee labeled clinical telemetry. The date appears on the [official page of Santiago, Dominican Republic](https://www.spaceappschallenge.org/2026/local-events/santiago-dominican-republic/), used as the calendar source, not as the team's venue. The [global event](https://www.spaceappschallenge.org/2026/) is scheduled for November 14 and 15. The schedule and local deliverables for Cajamarca must be confirmed with its organization.

**Problem and usefulness.** An astronaut finishes an exercise session. They have measurements, but need to understand whether their evolution matches the usual one for a comparable activity, whether a signal has problems and what information should be recorded for review. The project's hypothesis is that combining context, personal reference and explanation can improve that interpretation. This must be verified with usability tests; it is not presented as a demonstrated clinical benefit.

NASA documents research with vests for pulse and breathing, bands for temperature and other devices. For that reason the concept can rely on habitat devices, without assuming that all suits have the same sensors. [Wearable Tech for Space Station Research](https://www.nasa.gov/humans-in-space/wearable-tech-for-space-station-research/).

Local operation adds value for future missions: NASA describes communication delays of up to 20 minutes one way from Mars. The scenario does not presuppose that delay on the ISS or on all missions. [The Human Body in Space](https://www.nasa.gov/humans-in-space/the-human-body-in-space/).

**Core experience.** The application recognizes, or lets the user mark, the end of an activity. It compares subsequent measurements with comparable personal sessions and presents one of these states: expected pattern, sustained deviation or insufficient data. Each state includes context, evolution and signal quality. "Expected pattern" describes the signals analyzed; it does not certify the user's overall health.

Illustrative message example: "Heart rate remains above your reference for this recovery phase. The respiratory signal also departs from its pattern. Check the measurement and record how you feel." The interface must be able to explain what changed, since when and with respect to which reference.

**Proposed minimum data.**

| Input | Use in the prototype | Condition |
| --- | --- | --- |
| Heart rate | Trend and recovery | Record units, time and provenance |
| Respiratory rate | Complementary physiological context | Only if it exists in the source used |
| Activity and end of exercise | Compare similar situations | May be declared manually in the demo |
| Quality and age of each signal | Detect data loss and limit conclusions | Based on available flags or documented technical rules |
| Brief self-report | Record perceived exertion and discomfort | Do not automatically turn it into a diagnosis |

SpO₂ or temperature would be extensions if the resource justifies them. Skin temperature is not equivalent to core temperature. A table of per-second values also does not allow recognizing all sensor artifacts.

**MVP to build during the event.**

1. A status screen with two signals, activity, trend and data availability.
2. An explanation of each episode: observed values, reference, duration and signals that contributed to the alert.
3. A short self-report form and an illustrative review sequence: verify the signal, repeat the measurement when appropriate and record the episode for the medical officer.
4. An exportable local history with measurements, context and events.
5. A separate panel to replay records and activate synthetic scenarios identified as such.

The review sequence requires health advice before becoming a real-use protocol. For the hackathon it can remain explicitly illustrative. It is advisable to ask a health mentor to review the case, the terms and the actions; that one-off review does not constitute clinical validation.

The first version works with a simulated profile and local processing. Authentication, multiple accounts, physical integration of several sensors and a conversational assistant can wait. A web interface adaptable to tablet or laptop reduces implementation work.

**Analytical component and model.** Separate three responsibilities:

1. Data quality: recognize missing, stale or technically invalid signals. A failed signal must not hide an alert backed by another valid signal.
2. Explainable reference: compare recovery curves or trends with a personal baseline conditioned by activity. If history is missing, show "calibrating". Do not automatically update the reference with episodes flagged as anomalous.
3. Exploratory forecast: if enough series are available, train a simple regression that estimates heart rate at 30–60 seconds from the recent history and the available context. Compare against keeping the last value and extrapolating a simple trend.

A concrete training target would be "heart rate 60 seconds from now", with inputs computed exclusively from the past. The horizon is adjusted to the duration and quality of the data. If the model does not improve on the simple reference on held-out data, keep the simple reference.

A good numeric forecast does not demonstrate anticipation of an emergency. An anomaly score is also not a probability of disease. Demonstration alerts must have persistence, explicit criteria and parameters identified as experimental. Personalization alone does not guarantee medical safety; a clinical system would additionally require safety criteria reviewed by specialists.

**Data strategy and the October 28 decision.**

| Resource | Reasonable use | Relevant limit |
| --- | --- | --- |
| Official challenge resources | Determine the final case and support space-related decisions | Structure, variables, labels and permissions are not yet known |
| [PPG-DaLiA, UCI](https://archive.ics.uci.edu/dataset/495/ppg) | Explore signals and movement during activities of 15 participants; study pulse estimation | It therefore contains no diagnoses or labels of abnormal space recovery; download of approximately 2.7 GB |
| [BIDMC, PhysioNet](https://physionet.org/content/bidmc/1.0.0/) | Replay pulse, breathing and SpO₂; test ingestion and technical forecasting | 53 eight-minute records from hospital patients, not astronauts exercising |
| Own synthetic scenarios | Verify interface, data loss, alerts and the complete flow | They demonstrate software operation in simulation, not medical efficacy |

PPG-DaLiA includes ECG as a pulse reference, PPG and accelerometry; its published license is CC BY 4.0. BIDMC offers parameters at 1 Hz and CSV files under Open Data Commons Attribution. Each source requires keeping its attribution and checking compatibility with the submission. Do not mix data from different populations as if they were equivalent.

On the 28th, review: real access, license, variables, units, frequency, duration, person/session identifier, activity, labels and volume. The decision would be:

- If there is sufficient activity and recovery: keep the personal recovery case.
- If there are only physiological series: narrow to trend and quality monitoring, and evaluate technical forecasting without claiming abnormal recovery.
- If documents or other types of data predominate: adapt the case to the resource and demonstrate the platform through transparent simulation.

NASA data and documents must influence concrete product decisions. Record which resource justifies each signal, scenario or requirement, and which part comes from land-based or simulated data.

**Proposed three-minute demo.**

| Moment | Scenario | What must be clear |
| --- | --- | --- |
| 0:00–0:30 | Introduce astronaut and activity | Recovery question and personal reference |
| 0:30–1:05 | Usual recovery | The system considers the exercise context |
| 1:05–1:55 | Injected persistent deviation | Explains signals and duration; allows recording context and opening a review |
| 1:55–2:25 | Loss of a sensor | Shows insufficient data or partial analysis, without inventing measurements |
| 2:25–3:00 | Continue without internet and export episode | Local processing and summary available for later review |

All scenarios show provenance and simulation time. Replay can be accelerated by indicating the speed factor. It is advisable to use a scenario control for the presentation and reserve other scenarios for testing, so that the behavior does not depend only on the rehearsed script.

**Technical success criteria.** Measure synthetic events detected versus injected, false alerts per simulated hour and detection delay. Verify missing signals, clear messages and local continuity. If there is a forecast, measure mean absolute error in pulse units against the simple references.

Reserve complete participants or sessions for evaluation; avoid overlapping windows crossing training and test. For personalization, calibrate with an earlier segment and evaluate on an independent later segment. Also separate the simulator's seeds and variants. Results on simulation are reported as such.

A small usability test can measure how long it takes someone to identify what changed, which data are missing and what the next step shown is. This evaluates comprehension, not clinical safety. Do not set promised accuracy percentages before measuring.

**Work organization.** Distribute four roles, combinable according to the real size of the team: interface and experience; data and analysis; integration and simulation; research, validation and presentation. One person should look after integration and another the sources and limits of the claims, even if they also program.

Before the event: explore the challenge, study data, learn tools, identify health mentorship and confirm local rules on preparation. The guidance from [Space Apps Tel Aviv 2026](https://space.tau.ac.il/SpaceApps2026), published by its organizer, distinguishes prior exploration from building the project during the hackathon. This document is a preparation proposal; the permitted scope should be checked with Cajamarca.

During the event, distribute the effective time approximately as follows: 15% closing the case and data; 35% building the complete flow with explainable rules; 20% adding/evaluating the model if applicable; 15% testing and integrating; 15% preparing demo, sources and delivery. At the halfway point a complete walkthrough must already work. If it does not, reduce extensions and secure that walkthrough.

**Proposed pitch.** "Órbita helps astronauts interpret their recovery after an activity. It combines signals, context and a personal reference to explain sustained changes and keep a reviewable record, even without a connection. Our prototype demonstrates that flow and measures its technical behavior; the next step is to evaluate it with representative data and specialists."

The demonstrable contribution will be a personal, explainable and local interpretation flow. Clinical usefulness, its adaptation to different mission conditions and any land-based use will require later evaluation. For a team without health training, this delimitation allows contributing from software and data without basing the project on diagnoses it cannot yet support.
