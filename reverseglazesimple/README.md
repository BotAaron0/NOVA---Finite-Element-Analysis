# Reverse Glaze Simple

Find documented fired glaze combinations whose photographed colors resemble a target HEX color or image. All files for this tool live in `reverseglazesimple`; it is independent of the FEA pipeline.

This is retrieval from real combination charts, not a primary-color mixer or an unvalidated chemistry predictor. It preserves glaze order, coats, cone, documented atmosphere, clay body, and engobe. No AI service, API key, web server, or model training is required.

## Run in PowerShell

From the parent `fea gpt` folder:

```powershell
notepad .\reverseglazesimple\inputs.txt
.\reverseglazesimple\run.cmd
```

Fill in at least `target_color_hex` or `target_reference_image_path`. Set firing cone, atmosphere, clay, and engobe when known. Save Notepad before running. A minimal example is:

```ini
target_color_hex = #4A9FA5
target_cone = 6
firing_atmosphere = oxidation
clay_body_type = white_stoneware
engobe_or_slip = none
```

The ZIP path is already populated in `inputs.txt`; change it if the file moves. Other fields may remain blank. The archive is read in place and is not unpacked into arbitrary paths. Colors use a leading `#`; cone `06` is preserved and is different from cone `6`.

`run.cmd` invokes the PowerShell launcher with a process-scoped execution policy; it does not change your system policy. The launcher uses a suitable project environment or an existing bundled Codex Python runtime. Its inputs path is explicit and printed at launch.

The first run builds a local catalog from all PDFs. Later runs reuse the catalog after checking the archive SHA-256. Matching is much faster than initial indexing. All outputs go under `reverseglazesimple/outputs/` and remain ignored by Git.

To build the catalog before choosing a target:

```powershell
.\reverseglazesimple\run.cmd -Command index
```

Optional explicit input and output paths (prefer absolute paths when launching from outside this folder):

```powershell
.\reverseglazesimple\run.cmd -Inputs "C:\path\inputs.txt" -Output "C:\path\new-results"
```

Existing result files are protected. A fresh timestamped result directory is selected by default.

## Install on another computer

Use Python 3.11 or newer and run inside `reverseglazesimple`:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m glaze_matcher.cli
```

Dependencies: NumPy, Pillow, pdfplumber, and pypdfium2. Downloads require internet; matching and PDF processing are local. On Linux/macOS use `.venv/bin/python` instead. You do not need the FEA dependencies.

## Results

Each `outputs/match-TIMESTAMP/` folder contains:

| File | Contents |
| --- | --- |
| `report.html` | Open in a browser for ranked photos, recipes, palette swatches, and limitations |
| `matches.txt` | Plain-text recipes and source locations |
| `matches.json` | Machine-readable matches, scores, requested conditions, and unverified inputs |
| `inputs-used.txt` | Exact input-file snapshot |
| `match-01.jpg`, etc. | Source chart cells, including the fired vase and its original labels |

`outputs/catalog/catalog.json` contains every indexed combination and an audit of skipped pages/cells. Catalog photos are stored alongside it. Each result includes PDF filename, page, row, column, and extracted labels. Recognized layouts include three/four-column charts with right-side labels and older charts with footer labels. Other layouts are flagged for review instead of guessing recipes.

## Matching behavior

- **Overall color:** CIE76 distance between mean CIELAB colors in the central glazed vase body.
- **Dominant color:** CIE76 distance between the largest color clusters.
- **Multicolor pattern:** Symmetric, weighted nearest-palette color distance. This compares color distributions, not the spatial shape of a pattern.

The vase region is sampled rather than the little square showing an individual glaze. Sampling uses a central body inset to reduce background, rim, foot, and shadows. Five deterministic color clusters describe the observed color distribution. Camera lighting, reflections, print encoding, and display calibration still affect accuracy. A source crop is included for visual verification.

Known mismatches in cone, atmosphere, clay, application method, coat counts, drying, engobe, and allowed inventory are excluded. Unknown chart conditions remain eligible but are flagged explicitly. Atmosphere is never assumed to be oxidation merely because reduction is not stated. Missing user conditions leave that dimension unrestricted and add a warning.

Layer order is taken from each chart's **over/under** label, including an engobe where specified. It is not swapped to invent a new result. If inventory filtering is enabled, the required engobe must also be in `available_glazes`. Use exact product codes, with or without hyphens; product names may accompany them. Results are deduplicated by ordered recipe and documented conditions.

Both HEX and image may be supplied: HEX takes precedence for overall/dominant color, while multicolor matching uses the reference image. Crop reference images to the desired glaze region before matching; reference-image backgrounds are not automatically segmented. The selected target source is reported.

Scores are photo-color distances, **not confidence percentages**, chemistry predictions, or guarantees that a firing will match. Identical-looking photos can represent different physical conditions.

## What the charts cannot verify

The questionnaire also records dry thickness in mm, peak temperature, heating/cooling segments, kiln information, finish, opacity, texture, defects, intended use, and local-test paths. These supplied fields appear under `recorded_but_not_verified_or_modeled` in the output. They do **not** silently change predicted color.

The catalog does not contain calibrated thickness-response data, full firing schedules, measured optical properties, or food-contact suitability tests. Coat counts are not converted to millimeters; peak temperature is not converted to cone. Glaze names such as “Matte” are not treated as proof of the resulting combination's finish. Local-test folders and schedule files are recorded but not ingested by this version. Validate recommendations with test tiles under your own conditions.

## Tests

From this folder, using an environment with the dependencies installed:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Tests cover HEX parsing, cone leading zeros, validation, CIELAB reference values, palette metrics, under-order interpretation, unknown-atmosphere handling, real PDF rendering/extraction from a generated ZIP, vase-versus-swatch color isolation, cache reuse, inventory/cone filtering, result round trips, and output preservation. Dependency skips do not establish extraction correctness.
