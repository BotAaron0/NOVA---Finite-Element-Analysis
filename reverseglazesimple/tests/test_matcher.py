import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from glaze_matcher.config import read_inputs, cone

AVAILABLE = all(importlib.util.find_spec(n) for n in ("numpy", "PIL", "pdfplumber", "pypdfium2"))


def fixture_pdf():
    """A small PDF chart with colored fired-photo regions and separate swatches."""
    commands = ["BT /F1 10 Tf 20 760 Td (Cone 6 on White Stoneware body.) Tj ET",
                r"BT /F1 8 Tf 20 622 Td (Brush two \(2\) layers of base glaze. Then apply two \(2\) layers of top glaze, dry between coats.) Tj ET"]
    for row in range(3):
        for col in range(3):
            x = 18+col*192
            top = 201+row*180
            # True result blue, small standalone glaze swatch red.
            commands.extend([f"0.1 0.4 0.8 rg {x+10} {792-top-138} 100 135 re f",
                             f"1 0 0 rg {x+124} {792-top-60} 60 60 re f",
                             "0 0 0 rg"])
            lines = ["SW-110", "Oyster", "over", "SW-125", "Purple Mint"]
            if row == 2 and col == 2:
                lines[2] = "under"
            for j,line in enumerate(lines):
                commands.append(f"BT /F1 8 Tf {x+122} {792-top-77-j*11} Td ({line}) Tj ET")
    stream = "\n".join(commands).encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               f"<< /Length {len(stream)} >>\nstream\n".encode()+stream+b"\nendstream"]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data))
        data += f"{i} 0 obj\n".encode()+obj+b"\nendobj\n"
    start = len(data)
    data += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        data += f"{offset:010d} 00000 n \n".encode()
    data += f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode()
    return bytes(data)


class ConfigTests(unittest.TestCase):
    def test_hex_and_cone_leading_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.zip").write_bytes(b"test")
            path = root / "inputs.txt"
            path.write_text("# comment\ntarget_color_hex = #4A9FA5\ntarget_cone = 06\ncombination_zip_path = data.zip\n")
            config = read_inputs(path)
            self.assertEqual(config["target_color_hex"], "#4A9FA5")
            self.assertEqual(config["target_cone"], "06")
            self.assertNotEqual(cone("Cone 06"), cone("6"))
            self.assertEqual(config["combination_zip_path"], str(root / "data.zip"))

    def test_invalid_and_missing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.zip").touch()
            path = root / "inputs.txt"
            for addition in ("target_color_hex = red", "number_of_results = 0", "target_color_hex = #001122\nnumber_of_results = 2.5",
                             "base_dry_thickness_mm = nan", "unknown = 3", "target_cone = 6\ntarget_cone = 06", ""):
                path.write_text("combination_zip_path = data.zip\n"+addition)
                with self.subTest(addition=addition), self.assertRaises(ValueError):
                    read_inputs(path)


@unittest.skipUnless(AVAILABLE, "Install the reverseglazesimple dependencies")
class MatcherTests(unittest.TestCase):
    def test_lab_reference_values_and_palette_metric(self):
        import numpy as np
        from PIL import Image
        from glaze_matcher.colors import rgb_to_lab, describe, color_distance
        np.testing.assert_allclose(rgb_to_lab([255,255,255]), [100,0,0], atol=0.001)
        np.testing.assert_allclose(rgb_to_lab([0,0,0]), [0,0,0], atol=0.001)
        np.testing.assert_allclose(rgb_to_lab([255,0,0]), [53.2408,80.0925,67.2032], atol=0.001)
        blue = describe(Image.new("RGB",(20,20),"blue"))
        red = describe(Image.new("RGB",(20,20),"red"))
        for mode in ("overall_color", "dominant_color", "multicolor_pattern"):
            self.assertAlmostEqual(color_distance(blue,blue,mode),0)
            self.assertGreater(color_distance(blue,red,mode),20)

    def test_under_label_order_and_unknown_atmosphere(self):
        from glaze_matcher.catalog import cell_recipe, page_conditions
        conditions = page_conditions("Cone 6 on White Stoneware. two (2) layers of base glaze. apply two (2) layers of top glaze")
        recipe = cell_recipe("SW255 Gray Opal\nunder\nSW226 Pink Pearl\non EG005 Black Engobe",conditions)
        self.assertEqual(recipe["top"]["code"],"SW-226")
        self.assertEqual(recipe["base"]["code"],"SW-255")
        self.assertEqual(recipe["engobe"],"EG-005")
        self.assertEqual(conditions["atmosphere"],"unknown")

    def test_known_conditions_and_engobe_filter(self):
        from glaze_matcher.matcher import compatibility
        record = {"cone":"10", "atmosphere":"reduction", "clay_body":"white_stoneware",
                  "application_method":"brush", "dry_between_coats":"yes", "base_coats":2,
                  "top_coats":2, "base":{"code":"SW-125"}, "top":{"code":"SW-110"},
                  "engobe":"EG-005", "label_relation":"over"}
        inputs = {"material_selection":"any_in_dataset", "allow_documented_reverse_layer_order":"yes"}
        self.assertTrue(compatibility(record,inputs)[0])
        for field,value in (("firing_atmosphere","oxidation"), ("target_cone","6"),
                            ("engobe_or_slip","none"), ("allowed_base_coat_counts","3"),
                            ("excluded_glazes","SW125"), ("application_method","dip")):
            with self.subTest(field=field):
                self.assertFalse(compatibility(record,{**inputs,field:value})[0])
        inputs.update(material_selection="available_only", available_glazes="SW125, SW110")
        self.assertFalse(compatibility(record,inputs)[0])
        inputs["available_glazes"] += ",EG005"
        self.assertTrue(compatibility(record,inputs)[0])

    def test_zip_to_catalog_match_and_report(self):
        from glaze_matcher.catalog import build_catalog
        from glaze_matcher.matcher import match
        from glaze_matcher.report import write_report
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with zipfile.ZipFile(root / "charts.zip","w") as archive:
                archive.writestr("../chart.pdf",fixture_pdf())
            path = root / "inputs.txt"
            path.write_text("target_color_hex = #1A66CC\ntarget_cone = 6\nfiring_atmosphere = oxidation\ncombination_zip_path = charts.zip\n")
            inputs = read_inputs(path)
            catalog = build_catalog(root/"charts.zip",root/"catalog",lambda _:None)
            self.assertEqual(len(catalog["records"]),9)
            self.assertFalse(catalog["skipped"])
            # Blue vase, not red individual-glaze swatch, must be measured.
            rgb = catalog["records"][0]["descriptor"]["palette"][0]["rgb"]
            self.assertGreater(rgb[2],rgb[0]*3)
            self.assertEqual(build_catalog(root/"charts.zip",root/"catalog",lambda _:None)["archive_sha256"],catalog["archive_sha256"])
            result = match(catalog,inputs)
            self.assertEqual(result["compatible_records"],9)
            self.assertTrue(result["matches"][0]["condition_warnings"])
            self.assertLess(result["matches"][0]["photo_color_distance"],2)
            write_report(result,root/"catalog",root/"out",path)
            saved = json.loads((root/"out/matches.json").read_text())
            self.assertTrue((root/"out"/saved["matches"][0]["result_image"]).is_file())
            self.assertTrue((root/"out/report.html").exists())
            with self.assertRaises(ValueError):
                write_report(result,root/"catalog",root/"out",path)
            inputs["target_cone"] = "06"
            self.assertEqual(match(catalog,inputs)["matches"],[])
            inputs["target_cone"] = "6"
            inputs["material_selection"] = "available_only"
            inputs["available_glazes"] = "SW-110"
            self.assertEqual(match(catalog,inputs)["matches"],[])
            inputs["available_glazes"] = "SW-110,SW-125"
            self.assertTrue(match(catalog,inputs)["matches"])


if __name__ == "__main__":
    unittest.main()
