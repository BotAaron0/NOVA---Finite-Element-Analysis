import tempfile
import unittest
from pathlib import Path
from vase_stress.config import read_settings
from vase_stress.colors import stress_color


class CoreTests(unittest.TestCase):
    def settings(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.txt"
            path.write_text(text, encoding="utf-8-sig")
            return read_settings(path)

    def test_notepad_bom_and_comments(self):
        settings = self.settings("# material\nyoung_modulus_pa = 1000 # Pa\n")
        self.assertEqual(settings.young_modulus_pa, 1000)
        self.assertEqual(settings.gravity_m_s2, 9.81)

    def test_invalid_inputs(self):
        for text in ("density_kg_m3=-1", "poisson_ratio=0.5", "up_axis=q", "unknown=4", "model_scale=nan", "model_scale=1\nmodel_scale=2"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.settings(text)

    def test_color_anchors(self):
        from vase_stress.colors import color_scale, STOPS
        anchors = color_scale(1234)["anchors_pa"]
        for value, color in zip(anchors.values(), STOPS):
            self.assertEqual(stress_color(value, 1234), list(color) + [255])
        self.assertEqual(stress_color(0, 0), [0, 0, 255, 255])
        self.assertEqual(stress_color(9999, 1234), [255, 0, 0, 255])
        self.assertNotEqual(stress_color(1, 1000), stress_color(100, 1000))
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                stress_color(value, 1000)


if __name__ == "__main__":
    unittest.main()
