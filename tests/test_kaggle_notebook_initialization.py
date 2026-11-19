import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/c01_kaggle_cpu_smoke.ipynb"
SCRIPT = Path("scripts/kaggle_environment_smoke.py")


class KaggleNotebookInitializationTest(unittest.TestCase):
    def setUp(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        self.cells = {
            cell["id"]: "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        }
        self.scope = {}
        self.execute("config")

    def execute(self, cell):
        exec(compile(self.cells[cell], f"{NOTEBOOK.name}:{cell}", "exec"), self.scope)

    def test_missing_checkout_reports_actionable_error_before_import(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "SGBR-Reproduction"
            self.scope["CHECKOUT"] = missing
            with patch("importlib.util.spec_from_file_location") as import_script:
                with self.assertRaises(FileNotFoundError) as raised:
                    self.execute("initialize")
                import_script.assert_not_called()

        message = str(raised.exception)
        self.assertIn(str(missing / SCRIPT), message)
        self.assertIn("Attach the private Kaggle Dataset", message)
        self.assertIn("KAGGLE_DATASET_ROOT", message)
        self.assertIn("CHECKOUT", message)

    def test_unconfigured_source_reports_the_default_checkout_path(self):
        with patch.object(Path, "is_file", return_value=False):
            with self.assertRaises(FileNotFoundError) as raised:
                self.execute("initialize")
        self.assertIn(
            "/kaggle/working/SGBR-Reproduction/scripts/kaggle_environment_smoke.py",
            str(raised.exception),
        )

    def test_dataset_without_scripts_layout_reports_expected_file(self):
        with TemporaryDirectory() as directory:
            dataset_root = Path(directory)
            shutil.copyfile(ROOT / SCRIPT, dataset_root / SCRIPT.name)
            self.scope["KAGGLE_DATASET_ROOT"] = dataset_root
            with self.assertRaises(FileNotFoundError) as raised:
                self.execute("initialize")
            self.assertIn(str(dataset_root / SCRIPT), str(raised.exception))

    def test_loads_probe_from_each_explicit_source(self):
        for setting in ("KAGGLE_DATASET_ROOT", "CHECKOUT"):
            with self.subTest(setting=setting), TemporaryDirectory() as directory:
                root = Path(directory)
                script = root / SCRIPT
                script.parent.mkdir()
                shutil.copyfile(ROOT / SCRIPT, script)
                self.execute("config")
                self.scope[setting] = str(root)
                self.execute("initialize")
                self.assertEqual(self.scope["probe_script"], script)
                self.assertEqual(Path(self.scope["probe_module"].__file__), script)
                self.assertTrue(callable(self.scope["run"]))

    def test_rejects_two_configured_sources(self):
        self.scope.update(CHECKOUT="/some/checkout", KAGGLE_DATASET_ROOT="/some/dataset")
        with self.assertRaisesRegex(ValueError, "Set only one"):
            self.execute("initialize")


if __name__ == "__main__":
    unittest.main()
