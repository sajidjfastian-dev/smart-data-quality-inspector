"""Guard the dependency security baseline using only the standard library."""

from importlib.metadata import version
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SECURITY_PINS = {
    "pillow": "13.0.0",
    "anyio": "4.16.0",
    "certifi": "2026.10.23",
    "h11": "0.16.0",
    "idna": "3.20",
}


class DependencySecurityTests(unittest.TestCase):
    def test_security_versions_are_explicitly_pinned(self):
        requirements = {
            line.strip().lower()
            for line in (ROOT / "requirements.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for package, expected in SECURITY_PINS.items():
            with self.subTest(package=package):
                self.assertIn(f"{package}=={expected}", requirements)

    def test_installed_versions_match_security_pins(self):
        for package, expected in SECURITY_PINS.items():
            with self.subTest(package=package):
                self.assertEqual(version(package), expected)


if __name__ == "__main__":
    unittest.main()
