# MMASH · Sleep Episodes

The [episodes table](episodios_sueno.csv) makes it possible to reproduce a sleep summary in the interface. There are 22 episodes from 21 participants across the study's 22 folders. The `user_11` file contains only the header, while `user_1` contributes two episodes. The unit of analysis is an observed interval. The coverage of a single day limits the analysis of personal trends across multiple nights. [Coverage inventory](resumen.json)

| Fields | Interpretation |
| --- | --- |
| `subject_id`, `episode`, `source_member` | Participant, row position within their file, and source path within `MMASH.zip`. |
| `bed_day`, `bed_time`, `onset_day`, `onset_time`, `out_day`, `out_time` | Relative days and times as published for going to bed, sleep onset, and getting out of bed. |
| `bed_min`, `sleep_min`, `latency_min`, `waso_min` | Minutes in bed, minutes of sleep, sleep latency, and minutes awake after sleep onset. |
| `efficiency_pct`, `awakenings` | Published sleep efficiency percentage and number of awakenings. |
| `same_day_midnight_wrap` | Set to 1 for the four episodes whose wake-up time is earlier than their bedtime and that retain the same relative day in the original data. The `bed_min` field is used to present durations. |

To reproduce the table from the project root directory, run `.\\.venv\Scripts\python.exe ml\preparar_sueno.py`. The script verifies the SHA-256 hashes of the ZIP file and license against the [published checksums](SHA256SUMS.txt). It reads the rows from `sleep.csv` into memory, selects the relevant fields, and preserves the original values. The other files in the ZIP archive, including actigraphy and inter-beat intervals, remain available for other analyses. [Download receipt](fuente.json)

This table is derived from *Multilevel Monitoring of Activity and Sleep in Healthy People* v1.0.0, by Rossi, Da Pozzo, Menicagli, Tremolanti, Priami, Sirbu, Clifton, Martini, and Morelli (2020), PhysioNet. The original dataset and the derived table are distributed under the Open Data Commons Open Database License v1.0. The sample was collected from healthy young adults on Earth. [DOI and attribution](https://doi.org/10.13026/cerq-fc86) · [Dataset and authors' references](https://physionet.org/content/mmash/1.0.0/) · [License](LICENSE.txt)