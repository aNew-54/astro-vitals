ASTRO-VITALS — MVP and presentation strategy
===============================================

Scope reviewed on November 3, 2026 for the Cajamarca, Peru team. It replaces the initial Órbita exploration as the scope guide. The team brings together knowledge of software, data, design and electronics. The number of members, the available hours and the review of the messages by a health mentor are still pending.

[Version 0.1](prototype/README.md) implements the gateway, the on-board service and the astronaut console. The planned MVP adds Random Forest models, SQLite storage and an Earth node with a web view. The [data contract](CONTRATO_DE_DATOS.md) defines the inputs, outputs and sources per task. The [architecture](ARQUITECTURA_TECNICA.md) defines how to integrate them.

**Agreed concept.** A monitoring assistant for astronauts that brings together biometrics, activity and environmental context; generates indicative diagnostic hypotheses in demonstration scenarios; explains its evidence; and keeps a record shareable with Earth during communication delays or interruptions. It includes experimental prediction and a solar storm scenario.

The MVP's goal is to demonstrate that integrated experience. Hypotheses and projections produced with synthetic scenarios are presented as simulation results. The team will review the case with the resources announced for November 13, 2026.

**Prizes that guide the design.** The categories and descriptions in this table come from the three Space Apps Cajamarca images shared by the user. The priority is a planning recommendation, not a probability of winning nor a confirmation of eligibility, weightings or local/global selection mechanics.

| Category | Proposed priority | What ASTRO-VITALS would have to demonstrate |
| --- | --- | --- |
| Best Use of Technology | Primary | Functional integration of signals, local inference, explanation and synchronization with interrupted communication |
| Best Use of Storytelling | Secondary | A story understandable from both spacecraft and Earth that shows how a real open data point is used |
| Best Use of Data | Conditional on available resources | A substantive, traceable and useful use of NASA data in processing or interpretation; keep provenance and transformations |
| Galactic Impact | Potential complement | Relevant problem, defined user and plausible evaluation/adoption path; separate potential benefits from demonstrated ones |
| Best Use of Science | Potential complement | Explicit hypotheses, comparison with references, reproducible experiments and well-described limits |
| Most Inspirational | Complementary to the narrative | Connect with the human experience of receiving support when communication is limited |
| Local Impact | Future exploration | Investigate with local actors whether offline operation solves a real need in Cajamarca |
| Best Mission Concept | Partial affinity with the current scope | Explain where the system operates, its resources, users and mission constraints |
| Art & Technology | Secondary affinity | A substantive creative contribution that improves the experience; a space aesthetic alone is not the proposal |
| Global Community | Minor affinity for now | A real connection between communities; the two spacecraft–Earth views alone do not demonstrate that dimension |

The strategy is to build a single coherent solution. Technology and narrative reinforce each other with the same functions; they do not require creating additional products for each prize. Rigor in the data and measurements is kept as a cross-cutting criterion.

**Pitch promise.** "ASTRO-VITALS helps a crew interpret health and environmental signals when Earth receives information late. Our prototype integrates data, generates indicative hypotheses, explains the alerts and keeps episodes even without a connection."

**Functional scope.**

| Module | Minimum deliverable | Observable evidence |
| --- | --- | --- |
| Astronaut view | Pulse, breathing, activity, signal quality and communication status | Data update with times, units and availability |
| Indicative assessment | Simulated pattern with evidence, alternatives and missing information. The astronaut can record effort, discomfort or observations. | The episode indicates what changed, for how long and which signal requires review |
| Experimental prediction | HR at 60 s from the HR and RR history | Estimate identified by method and instant. Error in bpm against simple references on held-out records |
| Cabin context | Simulated CO₂ channel with identified origin | Can be compared in time with biometrics without claiming a nonexistent learned causality |
| Solar storm | Historical DONKI event and simulated local dosimeter in separate channels | The exposure alert is grounded in simulated local readings |
| Earth view and history | Episodes received, original measurements, explanation, times and delivery queue | After an outage, the record is recovered without duplicates or confusing old data with current data |
| Demo control | Real-speed replay, pause and selection of reproducible scenarios | The engine analyzes only the information available at the end of the window |

A fictional profile is used, with a TUI for the astronaut and a web app for Earth, connected to their respective nodes. The hypothesis, review and history flow is common to the scenarios. The communication simulation represents a link with delay and interruptions; it is not presented as a real DSN implementation.

**Data, simulation and model.** The demo's fusion brings together compatible signals within an explicit scenario. Real records may serve as a base, indicating what was modified. Arbitrarily joining land-based people with radiation from another mission does not produce observed clinical examples.

The generator has already produced the sessions with the four pattern classes defined in the contract and the per-window labels for training and evaluation. If inputs are missing or the classifier abstains, the planned interface will communicate the reason. [Fusion dataset](data/fusion_simulada/README.md)

An initial implementation can use a small classifier with trend and context variables. Rules check quality, persistence and configured limits; the classifier recognizes patterns; explanatory templates present observations and alternatives. Only attributions that are actually computed are shown. A synthetic classification percentage is not presented as a probability of disease.

For the classifier, separate fictional profiles and seeds before generating windows. Reserve noise, intensity and data-loss variants for evaluation. For the forecast, reserve complete BIDMC people or records and compare with keeping the last HR or extrapolating a trend.

The only variable that is forecast is HR at 60 s. If a six-hour environmental projection is included, it will be computed separately with an assumed exposure rate and that assumption will be shown.

**Low-scope solar scenario.**

1. Load the already stored historical DONKI SEP event. Keep the original date separate from the replay clock. [Selected event](data/donki/evento.json)
2. Show the event as context received from an external source. The application knows when it was received and how much time has elapsed; it does not depend on a live query to keep working.
3. Replay an independent simulated dosimeter series, distinguishing dose rate from accumulated dose and keeping consistent units. Do not derive personal dose directly from the DONKI event.
4. Process the readings through the common rules engine and store an episode with the evidence that triggered the alert. A remote solar event alone does not trigger a medical conclusion.
5. Allow "simulate move to shelter": change the rate according to an explicit scenario assumption. The accumulated dose does not decrease; it may increase more slowly.
6. If a projection is shown, state that it depends on the assumed rate and duration. Particle propagation, real shielding and biological damage are not modeled for this demo.

DONKI documents space weather events and analyses, including SEPs, and offers programmatic access. Its information is provided for research and prototypes. Source: [NASA CCMC — DONKI](https://ccmc.gsfc.nasa.gov/tools/DONKI/).

**Scenarios to prepare.**

| Scenario | Expected prototype behavior |
| --- | --- |
| Activity with expected physiological evolution | Recognize the context and show trends without triggering an alert just because of the scenario's name |
| Sustained physiological deviation with simulated environmental change | Present an indicative hypothesis, its observations, alternatives and illustrative review |
| Historical solar event with simulated dosimetry | Distinguish remote context from local measurement; explain the environmental alert and record the simulated action |
| Cross-cutting variant: missing or contradictory signal | Indicate what is missing and limit the conclusions of that channel without erasing alerts backed by other channels |

CO₂ and dosimetry alterations are presented in separate episodes. Instantaneous pulse changes are not attributed to radiation, and multiple simultaneous emergencies are not staged to increase drama.

**Tests that support the technology candidacy.**

| Test | Evidence to keep | Limit of interpretation |
| --- | --- | --- |
| Disconnection | Inference and recording continue with all necessary resources locally | Demonstrates the prototype's autonomy in the test performed |
| Reconnection | Comparison of episodes issued and received, order, identifiers and absence of duplicates | Demonstrates the link simulator's queue logic |
| Held-out variants | Results matrix, false alerts per simulated hour and detection delay | Describes performance on synthetic scenarios |
| Faulty sensor | Insufficient-data messages and preservation of other valid alerts | Describes handling of anticipated failures |
| Forecast, if trained | Error in the signal's units against a simple reference | Does not prove anticipation of illness |
| Comprehension | Short test with an outsider: identify change, source, age and next step | Evaluates clarity of use, not clinical safety |

No accuracy percentages or inference times are promised before measuring. The results sheet includes execution environment, scenario, reference used and limitations.

**Proposed demo narrative.** The rehearsal lasts about three minutes, adjustable to the time Cajamarca confirms. A single fictional astronaut connects two short scenes. At real speed, an identified prior history window can be loaded so that the model has context at the start. The screen keeps the date of the historical event.

| Approximate time | Action | What is communicated |
| --- | --- | --- |
| 0:00–0:20 | Introduce the astronaut and show the information Earth has | Concrete need and age of the information |
| 0:20–1:10 | Replay the physiological episode and open the indicative hypothesis | The engine uses signals, activity and evidence to interpret the scenario |
| 1:10–1:30 | Interrupt the link and record an on-board review | Autonomy solves an observable constraint |
| 1:30–2:20 | Explicitly switch to the solar scenario, open the NASA event and replay the dosimeter | The open data provides context; local exposure is identified as simulated |
| 2:20–2:40 | Simulate the shelter and show the exposure projection | Scenario decision and effect under visible assumptions |
| 2:40–3:00 | Reconnect and show the episode received on Earth and one measured metric | Traceable record and evidence of operation |

For Storytelling, the link to open data must be visible: chosen event, available observation, how it enters the story and what can or cannot be inferred from it. The narrative avoids invented medical outcomes, such as claiming a death was averted. The demonstrable outcome is that the crew interpreted the information, recorded their review and kept continuity during the outage.

**Best Use of Data.** On November 13 it will be reviewed whether an official resource contributes to a concrete comparison, estimation or interpretation. Its origin, access conditions, variables, transformations, function and limits will be documented.

The forecast examples are prepared with BIDMC and split by participant. PPG-DaLiA, MMASH and WESAD have local tables for possible extensions on activity, sleep and stress. [Preparation results](data/bidmc/README.md) · [Sources and use per task](DATOS_ALTERNATIVOS.md)

NASA-STD-3001 can ground specific rules if the applicable requirement, review, units, exposure and context are identified. The reference neither validates the model's hypotheses nor replaces their evaluation. [NASA — Human Spaceflight Standards](https://www.nasa.gov/ochmo/human-spaceflight-and-aviation-standards/).

**Impact and connection with Cajamarca.** As a hypothesis for future transfer, local processing and deferred sending could be useful in land-based situations with limited connectivity. To aspire to Local Impact, one would have to talk with local staff or institutions and describe a verified need, conditions of use and evaluation. This hypothesis does not imply that a pilot, validation or health benefit already exists. The MVP keeps the space context; it does not add a second land-based product.

**Organization and cuts.** Distribute combinable roles: interface/narrative, data/model, simulator/integration and evaluation/sources. The review by a health mentor focuses on the terms and the illustrative sequence; it is not presented as clinical validation. Before the event, sources and tools are studied and the permitted scope of preparation is confirmed with the organization.

During the build, distribute approximately 15% to case and data, 35% to the complete walkthrough, 20% to model and evaluation, 15% to integration and testing and 15% to rehearsal and delivery. At the halfway point a complete episode must work in both views. If time shrinks, prioritize the explained indicative hypothesis, a minimal solar episode, local continuity and synchronization; reduce live integrations, additional views and model complexity.

**Reviewable deliverables.** Executable application, short demo, reproducible instructions, data flow diagram, sources/licenses, evaluation sheet, simulator assumptions and an explanation of which part is historical data, simulated sensor or estimate. The prize selection guides this evidence and does not require modifying the product to cover all categories.
