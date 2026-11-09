"""Filter documented conditions and rank observed fired-result photographs."""
from .config import codes
from .colors import color_distance, describe

OPERATIONAL = set("""target_color_hex target_reference_image_path color_match_priority combination_zip_path
recommendation_mode number_of_results target_cone firing_atmosphere clay_body_type engobe_or_slip
application_method allowed_base_coat_counts allowed_top_coat_counts dry_between_coats
allow_documented_reverse_layer_order material_selection available_glazes excluded_glazes""".split())


def target_descriptor(inputs):
    from PIL import Image
    image_path = inputs.get("target_reference_image_path")
    if image_path and (not inputs.get("target_color_hex") or inputs["color_match_priority"] == "multicolor_pattern"):
        with Image.open(image_path) as image:
            return describe(image), "reference image (entire image; crop to desired glazed area first)"
    value = inputs["target_color_hex"].lstrip("#")
    rgb = tuple(int(value[i:i+2], 16) for i in (0,2,4))
    return describe(Image.new("RGB", (16,16), rgb)), "HEX color"


def normalize_body(value):
    return value.lower().strip().replace(" ", "_")


def compatibility(record, inputs):
    warnings = []
    for field, target in (("cone", inputs.get("target_cone")),
                          ("atmosphere", inputs.get("firing_atmosphere")),
                          ("clay_body", normalize_body(inputs.get("clay_body_type", ""))),
                          ("application_method", inputs.get("application_method")),
                          ("dry_between_coats", inputs.get("dry_between_coats"))):
        if not target or target == "unknown":
            continue
        actual = record[field]
        if actual in (None, "unknown"):
            warnings.append(f"Requested {field}={target}; chart does not specify it")
        elif actual != target:
            return False, []
    for field, requested in (("base_coats", "allowed_base_coat_counts"),
                             ("top_coats", "allowed_top_coat_counts")):
        if inputs.get(requested):
            allowed = {int(v) for v in inputs[requested].split(",")}
            if record[field] is None:
                warnings.append(f"Chart does not specify {field}")
            elif record[field] not in allowed:
                return False, []
    substrate = inputs.get("engobe_or_slip", "").strip()
    if substrate:
        selected = codes(substrate)
        if substrate.lower() == "none":
            if record["engobe"] != "none":
                return False, []
        elif not selected:
            # Never assert a name-only or unrecognized slip matches a chart code.
            warnings.append("Engobe/slip name could not be verified; use an EG product code or none")
        elif record["engobe"] not in selected:
            return False, []
    needed = {record["base"]["code"], record["top"]["code"]}
    if record["engobe"] != "none":
        needed.add(record["engobe"])
    if needed & set(codes(inputs.get("excluded_glazes", ""))):
        return False, []
    if inputs["material_selection"] == "available_only":
        if not needed <= set(codes(inputs.get("available_glazes", ""))):
            return False, []
    if inputs["allow_documented_reverse_layer_order"] == "no" and record["label_relation"] == "under":
        return False, []
    return True, warnings


def match(catalog, inputs):
    target, target_source = target_descriptor(inputs)
    results, seen = [], set()
    for record in catalog["records"]:
        compatible, warnings = compatibility(record, inputs)
        if not compatible:
            continue
        score = color_distance(target, record["descriptor"], inputs["color_match_priority"])
        results.append({**record, "photo_color_distance": score, "condition_warnings": warnings})
    results.sort(key=lambda item: (item["photo_color_distance"], item["id"]))
    selected = []
    for record in results:
        key = (record["base"]["code"], record["top"]["code"], record["cone"],
               record["atmosphere"], record["engobe"], record["base_coats"], record["top_coats"])
        if key in seen:
            continue
        seen.add(key)
        selected.append(record)
        if len(selected) >= inputs["number_of_results"]:
            break
    warnings = ["Ranks observed photo colors, not chemistry predictions or guaranteed fired colors.",
                "Lighting, glaze flow, body texture, and highlights affect photographed color.",
                "Application thickness in mm and full kiln schedules are not documented in this catalog.",
                "Missing source conditions remain unverified; known mismatches are excluded."]
    for field in ("target_cone", "firing_atmosphere", "clay_body_type", "engobe_or_slip"):
        if not inputs.get(field) or inputs[field] == "unknown":
            warnings.append(f"No {field} provided; candidates may span different conditions")
    unverified = {key: value for key, value in inputs.items() if value and key not in OPERATIONAL}
    if inputs.get("target_color_hex") and inputs.get("target_reference_image_path"):
        warnings.append(f"Both target inputs were supplied; matching uses {target_source}")
    return {"target": target, "target_source": target_source, "inputs": inputs,
            "catalog_archive_sha256": catalog["archive_sha256"], "catalog_schema": catalog["schema"],
            "metric": "CIE76 Delta E for overall/dominant; symmetric palette distance for multicolor",
            "catalog_records": len(catalog["records"]), "compatible_records": len(results),
            "review_items": len(catalog["skipped"]), "warnings": warnings,
            "recorded_but_not_verified_or_modeled": unverified, "matches": selected}
