"""Write portable HTML, JSON, and plain-text recommendations."""
import html
import json
import shutil
from pathlib import Path


def write_report(result, catalog_dir, output, input_path, input_bytes=None):
    output, catalog_dir = Path(output), Path(catalog_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Result output folder is not empty; choose a fresh --output folder")
    output.mkdir(parents=True, exist_ok=True)
    (output / "inputs-used.txt").write_bytes(input_bytes if input_bytes is not None else Path(input_path).read_bytes())
    escape = lambda value: html.escape(str(value))
    cards, lines = [], ["GLAZE MATCH RESULTS", f"Target: {result['inputs'].get('target_color_hex') or result['target_source']}",
                        f"Compatible samples: {result['compatible_records']}/{result['catalog_records']}", ""]
    for rank, item in enumerate(result["matches"], 1):
        context = f"match-{rank:02d}.jpg"
        shutil.copyfile(catalog_dir / item["context_image"], output / context)
        item["result_image"] = context
        base = f"{item['base']['code']} {item['base']['name']}"
        top = f"{item['top']['code']} {item['top']['name']}"
        condition = f"Cone {item['cone']}; atmosphere {item['atmosphere']}; body {item['clay_body']}; engobe {item['engobe']}"
        recipe = f"{item['base_coats'] or 'unspecified'} coats {base}, dry, then {item['top_coats'] or 'unspecified'} coats {top}"
        source = f"{item['source_pdf']}, page {item['page']}, row {item['row']}, column {item['column']}"
        lines.extend([f"{rank}. {top} OVER {base}", f"   Photo distance: {item['photo_color_distance']:.2f}",
                      f"   {recipe}", f"   {condition}", f"   Source: {source}",
                      *[f"   UNVERIFIED: {v}" for v in item["condition_warnings"]], ""])
        swatches = "".join(f'<span class="swatch" style="background:{p["hex"]}" title="{p["hex"]} ({p["weight"]:.0%})"></span>'
                           for p in item["descriptor"]["palette"])
        cautions = "".join(f"<li>{escape(v)}</li>" for v in item["condition_warnings"])
        cards.append(f'''<article><img src="{context}" alt="Source chart cell with fired result and layer labels">
<div><h2>{rank}. {escape(top)}<br><small>over {escape(base)}</small></h2>
<p>Photo color distance: <strong>{item['photo_color_distance']:.2f}</strong> (lower is closer)</p>
<div>{swatches}</div><p>{escape(recipe)}</p><p>{escape(condition)}</p><ul>{cautions}</ul>
<p class="source">{escape(source)}</p></div></article>''')
    if not cards:
        cards.append("<p>No documented combinations satisfy the supplied filters. Review cone, inventory, substrate and coat constraints; conditions were not silently relaxed.</p>")
        lines.append("No documented combinations satisfy the supplied filters.")
    warnings = "".join(f"<li>{escape(v)}</li>" for v in result["warnings"])
    unverified = "".join(f"<li><b>{escape(k)}</b>: {escape(v)}</li>" for k,v in result["recorded_but_not_verified_or_modeled"].items())
    target_swatches = "".join(f'<span class="swatch" style="background:{p["hex"]}" title="{p["hex"]}"></span>' for p in result["target"]["palette"])
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Glaze matches</title><style>body{{font:16px/1.55 system-ui,sans-serif;background:#f6f4ef;color:#212b2a;max-width:1050px;margin:auto;padding:28px}}
h1{{margin-bottom:4px}}h2{{font-size:21px}}small,.source{{color:#52605d}}article{{display:flex;gap:28px;background:white;border:1px solid #d9ded8;border-radius:14px;margin:22px 0;padding:22px}}
article img{{width:230px;object-fit:contain;align-self:flex-start}}.swatch{{display:inline-block;width:36px;height:27px;border:1px solid #999;margin-right:4px;border-radius:4px}}
details{{background:#e9ece6;padding:14px;border-radius:8px;margin:16px 0}}.source{{font-size:12px;overflow-wrap:anywhere}}@media(max-width:650px){{article{{flex-direction:column}}article img{{width:100%;max-width:300px}}}}</style>
<h1>Documented glaze matches</h1><p>Target: {escape(result['inputs'].get('target_color_hex') or result['target_source'])} {target_swatches}</p>
<p>{result['compatible_records']} compatible photographed results from {result['catalog_records']} indexed combinations. Scores are photo distances, not success probabilities.</p>
<details open><summary>Conditions and limits</summary><ul>{warnings}</ul></details>
{''.join(cards)}<details><summary>Provided inputs not verified or modeled from the chart data</summary><ul>{unverified or '<li>None</li>'}</ul></details>
<p>Source charts skipped or flagged for review: {result['review_items']}. See catalog.json for the extraction audit. A test tile is needed to verify the physical result.</p></html>'''
    (output / "report.html").write_text(document, encoding="utf-8")
    (output / "matches.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines.extend(["LIMITATIONS", *result["warnings"], "", "RECORDED BUT NOT VERIFIED OR MODELED",
                  *[f"{k} = {v}" for k,v in result["recorded_but_not_verified_or_modeled"].items()]])
    (output / "matches.txt").write_text("\n".join(lines), encoding="utf-8")
