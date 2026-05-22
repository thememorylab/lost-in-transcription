# Lost in Transcription: Underlining, Meaning, and the Limits of Handwritten Text Recognition in Norwegian Personal Letters

Code and data repository for a bachelor thesis in Archival Science, OsloMet, 2026.

This repository contains the detection scripts, ground truth annotations, and results used to investigate whether vision-based multimodal AI can detect underlining omitted from HTR transcriptions of Norwegian handwritten personal letters.

## Dataset

## Dataset

Letters are drawn from the **NorHand dataset**, published openly by the National Library of Norway. The sample consists of 40 personal letters purposively selected from the dataset, all of which contain at least one instance of underlining in the manuscript, with variation in writers, periods (1820–1950), registers, and the clarity and form of the underlining.

The letter images and XML transcriptions are not included in this repository due to file size constraints. They can be downloaded directly from:

- **Citation:** Maarand et al. (2022). https://doi.org/10.5281/zenodo.10255840
- **Licence:** Creative Commons Attribution (CC-BY)

Once downloaded, place the letter images and XML files in `letter-analyser/Letters/` to run the detection scripts.

## Repository Structure

```
├── analyse_letters_claude.py       # Detection script — Claude Opus 4.7 (Anthropic)
├── compare_results.py              # Compares detection results against ground truth
├── convert_groundtruth.py          # Converts ground truth spreadsheet to JSON
├── ground_truth.csv                # Manual annotation ground truth (spreadsheet)
├── ground_truth.json               # Manual annotation ground truth (JSON)
├── results_claude.json             # Detection results from Claude Opus 4.7
├── comparison_claude.json          # Accuracy comparison against ground truth
├── requirements.txt                # Python dependencies
├── LICENSE                         # CC-BY 4.0 licence
└── README.md                       # This file
```

## Method

Each letter image is divided into six horizontal strips, allowing the model to examine a smaller, more detailed portion of the letter at a time. This improves detection of subtle underlinings and reduces false positives compared to sending the full image. Plain text is extracted from the PAGE XML files and provided to the model as a spelling reference.

Detection was performed using **Claude Opus 4.7** (`claude-opus-4-7`) by Anthropic.

## Results

Detection against 89 manually annotated underlinings across 40 letters.

**Full sample (40 letters):**

| Metric | Score |
|--------|-------|
| Precision | 0.725 |
| Recall | 0.742 |
| F1 Score | 0.733 |

Performance varied considerably across letters:

- 20 letters returned a perfect F1 score (1.0)
- Four letters returned scores between 0.75 and 0.999
- 13 letters returned moderate scores (0.50–0.74)
- Two letters returned scores below 0.50
- One letter produced no detections (F1 undefined)

The lowest-scoring letters share visual conditions documented during manual annotation as likely to compromise detection: heavy decorative flourishes, verso ink bleed, or handwriting styles in which underlining visually merges with other marks.

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file with your Anthropic API key:

```
ANTHROPIC_API_KEY=your-key-here
```

**Never commit your `.env` file** — it is listed in `.gitignore`.

## Running the Detection

```bash
python3 analyse_letters_claude.py --folder ./letter-analyser/Letters --output results_claude.json
```

## Evaluating Results

Convert your ground truth spreadsheet to JSON:

```bash
python3 convert_groundtruth.py --input ground_truth.csv --output ground_truth.json
```

Compare detection results against ground truth:

```bash
python3 compare_results.py --ground_truth ground_truth.json --results results_claude.json --output comparison_claude.json
```

## Output Format

Each detected underlining is returned as a JSON object:

```json
{
  "text": "en Deel",
  "spans_multiple_words": true,
  "spans_line_break": false,
  "position": "strip 3",
  "confidence": "certain"
}
```

## Licence

CC-BY 4.0 — see `LICENSE`. Consistent with the NorHand dataset licence.

## Acknowledgements

Detection scripts were developed with coding assistance from Claude Sonnet 4.6 (Anthropic) via claude.ai. Underlining detection was performed using Claude Opus 4.7 (Anthropic) via the Anthropic API. All methodological decisions were made by the author.

## Author

Bachelor candidate, Archival Science
Oslo Metropolitan University, 2026
