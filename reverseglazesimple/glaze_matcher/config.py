"""Read the single editable questionnaire without losing HEX prefixes."""
import math
import re
from pathlib import Path

KEYS = set("""target_color_hex target_reference_image_path target_description
color_match_priority preferred_finish preferred_opacity preferred_texture
combination_zip_path recommendation_mode number_of_results clay_brand_and_product
clay_body_type clay_fired_color bisque_cone bisque_peak_temperature_c engobe_or_slip
engobe_or_slip_coats surface_orientation surface_texture target_cone peak_temperature_c
firing_atmosphere kiln_type firing_program_name firing_schedule_file_path heating_segments
peak_hold_minutes cooling_mode cooling_segments reduction_details witness_cone_result
application_method allowed_base_coat_counts allowed_top_coat_counts base_dry_thickness_mm
top_dry_thickness_mm total_dry_glaze_thickness_mm dry_between_coats base_dip_seconds
top_dip_seconds glaze_slurry_specific_gravity layer_overlap allow_documented_reverse_layer_order
material_selection available_glazes excluded_glazes unwanted_effects intended_use additional_notes
local_test_data_folder photo_lighting color_reference_card""".split())

CODE = re.compile(r"\b(SW|EL|CG|SC|FN|EG|S)\s*-?\s*(\d{2,4})\b", re.I)


def codes(text):
    return [f"{prefix.upper()}-{number}" for prefix, number in CODE.findall(text)]


def cone(text):
    value = re.sub(r"^cone\s*", "", text.strip(), flags=re.I)
    if value and not re.fullmatch(r"(?:0[1-9]|0[12]\d|[1-9]|1\d)", value):
        raise ValueError("target_cone must be a cone number such as 06, 6, or 10")
    return value


def read_inputs(path, require_target=True, contents=None):
    path = Path(path).resolve()
    values = {}
    text = contents.decode("utf-8-sig") if contents is not None else path.read_text(encoding="utf-8-sig")
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"')
        if not separator or key not in KEYS or key in values:
            raise ValueError(f"Invalid or duplicate input on line {number}: {key}")
        values[key] = value
    for key, allowed, default in [
            ("color_match_priority", {"overall_color", "dominant_color", "multicolor_pattern"}, "overall_color"),
            ("recommendation_mode", {"tested_only"}, "tested_only"),
            ("material_selection", {"available_only", "any_in_dataset"}, "any_in_dataset"),
            ("firing_atmosphere", {"oxidation", "reduction", "neutral", "unknown", ""}, ""),
            ("allow_documented_reverse_layer_order", {"yes", "no"}, "yes")]:
        values[key] = values.get(key) or default
        if values[key] not in allowed:
            raise ValueError(f"{key} must be one of: {', '.join(sorted(allowed))}")
    target = values.get("target_color_hex", "")
    if target and not re.fullmatch(r"#[0-9a-fA-F]{6}", target):
        raise ValueError("target_color_hex must contain six HEX digits, e.g. #4A9FA5")
    for key in ("combination_zip_path", "target_reference_image_path", "firing_schedule_file_path", "local_test_data_folder"):
        if values.get(key):
            location = Path(values[key])
            values[key] = str((path.parent / location).resolve() if not location.is_absolute() else location)
            if not Path(values[key]).exists():
                raise ValueError(f"{key} does not exist: {values[key]}")
    if not values.get("combination_zip_path"):
        raise ValueError("Set combination_zip_path in inputs.txt")
    if require_target and not (target or values.get("target_reference_image_path")):
        raise ValueError("Set target_color_hex or target_reference_image_path in inputs.txt")
    values["target_cone"] = cone(values.get("target_cone", ""))
    try:
        count = int(values.get("number_of_results") or 5)
    except ValueError:
        raise ValueError("number_of_results must be an integer") from None
    if not 1 <= count <= 50:
        raise ValueError("number_of_results must be between 1 and 50")
    values["number_of_results"] = count
    for key, value in values.items():
        if value and (key.endswith(("_mm", "_seconds", "_temperature_c", "_minutes")) or key == "glaze_slurry_specific_gravity"):
            try:
                numeric = float(value)
            except ValueError:
                raise ValueError(f"{key} must be a numeric measurement") from None
            if not math.isfinite(numeric) or numeric < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
    for key in ("allowed_base_coat_counts", "allowed_top_coat_counts"):
        if values.get(key) and not re.fullmatch(r"[1-9]\d*(?:\s*,\s*[1-9]\d*)*", values[key]):
            raise ValueError(f"{key} must be positive coat counts separated by commas")
    for key in ("available_glazes", "excluded_glazes"):
        if values.get(key):
            for item in values[key].split(","):
                if not codes(item):
                    raise ValueError(f"{key}: missing a product code in {item!r}")
    if values["material_selection"] == "available_only" and not codes(values.get("available_glazes", "")):
        raise ValueError("available_only requires product codes in available_glazes")
    return values
