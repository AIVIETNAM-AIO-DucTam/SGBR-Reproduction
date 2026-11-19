import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch


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
        self.execute("github-checkout")

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

    def test_unconfigured_source_uses_private_checkout(self):
        with patch.dict(self.scope, prepare_project_checkout=Mock(return_value="a" * 40)):
            with patch.object(Path, "is_file", return_value=False):
                with self.assertRaises(FileNotFoundError) as raised:
                    self.execute("initialize")
            self.scope["prepare_project_checkout"].assert_called_once_with(
                Path("/kaggle/working/SGBR-Reproduction"), "main", False
            )
        self.assertIn(
            "/kaggle/working/SGBR-Reproduction/scripts/kaggle_environment_smoke.py",
            str(raised.exception),
        )

    def test_fetch_uses_temporary_askpass_and_sanitizes_errors(self):
        fake_secret = "local-test-secret"
        client = Mock()
        client.get_secret.return_value = fake_secret
        kaggle_secrets = SimpleNamespace(UserSecretsClient=lambda: client)
        askpass_paths = []

        def fake_git(folder, *args, env):
            self.assertNotIn(fake_secret, " ".join(args))
            self.assertIn(self.scope["PROJECT_URL"], args)
            self.assertIn("credential.helper=", args)
            self.assertNotIn("GIT_TRACE", env)
            askpass = Path(env["GIT_ASKPASS"])
            askpass_paths.append(askpass)
            self.assertNotIn(fake_secret, askpass.read_text())
            for prompt, expected in (
                ("Username for 'https://github.com': ", "x-access-token"),
                ("Password for 'https://x-access-token@github.com': ", fake_secret),
            ):
                response = subprocess.run([str(askpass), prompt], env=env, capture_output=True, text=True)
                self.assertEqual((response.returncode, response.stdout.strip()), (0, expected))
            remote = subprocess.run(
                [str(askpass), "Password for 'https://x-access-token@other.test': "],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual((remote.returncode, remote.stdout), (1, ""))
            return SimpleNamespace(returncode=128, stderr=f"{reason} {fake_secret}")

        with patch.dict(sys.modules, kaggle_secrets=kaggle_secrets):
            with patch.dict("os.environ", {"GIT_TRACE": "1"}):
                with patch.dict(self.scope, project_git=fake_git):
                    for reason, message in (
                        ("Could not resolve host", "Enable Internet"),
                        ("Authentication failed", "Contents: Read"),
                        ("couldn't find remote ref", "GITHUB_REF"),
                    ):
                        with self.subTest(reason=reason):
                            with self.assertRaisesRegex(RuntimeError, message) as raised:
                                self.scope["fetch_project"](Path("."), "refs/heads/main")
                            self.assertNotIn(fake_secret, str(raised.exception))
        client.get_secret.assert_called_with("GITHUB_TOKEN")
        self.assertTrue(all(not path.exists() for path in askpass_paths))

    def test_missing_secret_has_setup_instructions(self):
        client = Mock()
        client.get_secret.side_effect = RuntimeError("internal secret-service error")
        with patch.dict(sys.modules, kaggle_secrets=SimpleNamespace(UserSecretsClient=lambda: client)):
            with self.assertRaisesRegex(RuntimeError, "grant this notebook access") as raised:
                self.scope["fetch_project"](Path("."), "refs/heads/main")
        self.assertTrue(raised.exception.__suppress_context__)

    def test_checks_out_branch_and_sha_and_reuses_matching_head(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote"
            target = root / "SGBR-Reproduction"
            remote.mkdir()

            def git(folder, *args):
                return subprocess.run(
                    ["git", "-C", str(folder), *args], check=True, capture_output=True, text=True
                ).stdout.strip()

            git(remote, "init", "-b", "main")
            git(remote, "config", "user.email", "test@example.com")
            git(remote, "config", "user.name", "Local Regression Test")
            git(remote, "commit", "--allow-empty", "-m", "first")
            first = git(remote, "rev-parse", "HEAD")
            git(remote, "commit", "--allow-empty", "-m", "second")
            second = git(remote, "rev-parse", "HEAD")

            def fetch(folder, revision):
                git(folder, "fetch", "--depth=1", "--no-tags", "--", remote.as_uri(), revision)

            prepare = self.scope["prepare_project_checkout"]
            with patch.dict(self.scope, fetch_project=Mock(side_effect=fetch)):
                self.assertEqual(prepare(target, "main"), second)
                self.assertEqual(prepare(target, "main"), second)
                self.scope["fetch_project"].assert_called_once()
                self.assertEqual(prepare(target, first), first)
                self.assertEqual(prepare(target, first), first)
                self.assertEqual(self.scope["fetch_project"].call_count, 2)
                self.assertEqual(prepare(target, "main", refresh=True), second)
            self.assertEqual(git(target, "remote", "get-url", "origin"), self.scope["PROJECT_URL"])
            self.assertEqual(self.scope["project_commit"](target), second)

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
