import io
import json
import os
import signal
import sys
import time
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
    import sgbr_c01_e1_integrated as pipeline


class IntegratedNotebookTest(unittest.TestCase):
    def test_notebook_keeps_the_reviewed_private_checkout_bootstrap(self):
        def bootstrap(name):
            nb = json.loads((ROOT / "notebooks" / name).read_text())
            for cell in nb["cells"]:
                if cell["cell_type"] == "code":
                    compile("".join(cell["source"]), name, "exec")
            return next(cell["source"] for cell in nb["cells"] if cell["id"] == "github-checkout")

        self.assertEqual(
            bootstrap("SGBR_C01_E1_Integrated.ipynb"), bootstrap("c01_kaggle_cpu_smoke.ipynb")
        )

    def test_apt_is_used_only_when_maven_is_missing(self):
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            with (
                patch.object(pipeline.shutil, "which", side_effect=[None, "/usr/bin/mvn"]),
                patch.object(pipeline.subprocess, "run") as command,
                patch.object(pipeline.c01, "run", return_value={"exit_code": 0}),
            ):
                self.assertEqual(pipeline.select_maven(cache), Path("/usr/bin/mvn"))
                self.assertEqual([call.args[0] for call in command.call_args_list], [
                    ["apt-get", "update", "-qq"], ["apt-get", "install", "-y", "maven"],
                ])
            with (
                patch.object(pipeline.shutil, "which", return_value="/usr/bin/mvn"),
                patch.object(pipeline.subprocess, "run") as command,
                patch.object(pipeline.c01, "run", return_value={"exit_code": 0}),
            ):
                self.assertEqual(pipeline.select_maven(cache), Path("/usr/bin/mvn"))
                command.assert_not_called()

    def test_cache_revalidates_the_jar_bytes(self):
        with TemporaryDirectory() as directory:
            artifacts = Path(directory)
            jar = artifacts / pipeline.FAT_JAR_NAME
            with zipfile.ZipFile(jar, "w") as file:
                file.writestr("moa/DoTask.class", b"test")
                file.writestr("moa/classifiers/meta/StreamingGradientBoostedTrees.class", b"test")
            tools = {"java_version": "jdk", "maven_version": "mvn"}
            (artifacts / "moa_build.json").write_text(json.dumps({
                "upstream_commit": "pinned", "build_java_version": "jdk",
                "build_maven_version": "mvn", "sha256": pipeline.digest(jar),
            }))
            with patch.object(pipeline.subprocess, "run") as command:
                self.assertTrue(pipeline.build_or_reuse(
                    artifacts, artifacts, "mvn", tools, "pinned",
                )[1]["reused"])
                command.assert_not_called()
            with zipfile.ZipFile(jar, "a") as file:
                file.writestr("changed", b"checksum differs")
            with patch.object(pipeline.subprocess, "run", return_value=Mock(returncode=1)) as command:
                with self.assertRaisesRegex(RuntimeError, "MOA build failed"):
                    pipeline.build_or_reuse(artifacts, artifacts, "mvn", tools, "pinned")
                command.assert_called_once()

    def test_c01_gates_e1_and_passes_only_the_verified_artifact(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            java = root / "jdk/bin/java"
            jar = root / "moa.jar"
            checksum = "0" * 64
            tools = {"java_version": "jdk", "maven_version": "mvn"}
            moa = {"sha256": checksum, "reused": False, "matches_reference_sha256": False}

            def run_e1(args):
                values = dict(zip(args[::2], args[1::2]))
                self.assertEqual(values["--moa-jar"], str(jar))
                self.assertEqual(values["--moa-sha256"], checksum)
                self.assertEqual(values["--java"], str(java))
                self.assertEqual(values["--dataset"], "NZEnergy")
                self.assertEqual(values["--learner"], "SGBT(ARFReg(FIRTDD))")
                self.assertEqual(values["--seed"], "1")
                self.assertEqual(values["--expected-instances"], "3100666")
                self.assertNotIn("--timeout-seconds", args)
                Path(values["--manifest"]).write_text('{"status": "interrupted"}')
                return 1

            with (
                patch.object(pipeline, "provision", return_value=(java, "mvn", tools)),
                patch.object(pipeline, "tool_versions", return_value={}),
                patch.object(pipeline, "upstream_checkout", return_value=(root, "pinned")),
                patch.object(pipeline, "build_or_reuse", return_value=(jar, moa)),
                patch.object(pipeline.c01, "main", return_value=0),
                patch.object(pipeline.e1, "main", side_effect=run_e1) as runner,
                patch.object(pipeline, "smoke") as smoke,
            ):
                smoke.side_effect = RuntimeError("broken smoke")
                with self.assertRaisesRegex(RuntimeError, "broken smoke"):
                    pipeline.run_pipeline(root, "project-commit")
                runner.assert_not_called()
                smoke.side_effect = None
                smoke.return_value = {"passed": True, "processed_instances": 8}
                self.assertEqual(pipeline.run_pipeline(root, "project-commit"), 1)
                runner.assert_called_once()
            manifests = root / "results/manifest"
            environment = json.loads((manifests / "environment.json").read_text())
            experiment = json.loads((manifests / "e1_memory_feasibility.json").read_text())
            self.assertTrue(environment["notebook_smoke_passed"])
            self.assertEqual(experiment["status"], "interrupted")
            self.assertEqual(experiment["project_git_commit"], "project-commit")

    def test_carriage_returns_and_split_percentage(self):
        e1 = pipeline.e1
        carry, percent = e1.read_progress(io.BytesIO(b"\r7.15% Evaluating learner\r95."), b"", None)
        self.assertEqual(percent, 7.15)
        _, percent = e1.read_progress(io.BytesIO(b"06% Evaluating learner\r"), carry, percent)
        self.assertEqual(percent, 95.06)

    def test_interrupt_keeps_raw_log_estimate_and_signal(self):
        e1 = pipeline.e1
        with TemporaryDirectory() as directory:
            work = Path(directory)
            log = b"\r95.06% Evaluating learner\r"
            program = f"import sys,time; sys.stdout.buffer.write({log!r}); sys.stdout.flush(); time.sleep(30)"
            result = {
                "command": [sys.executable, "-c", program],
                "dataset": {"expected_instances": 3100666},
            }

            def interrupt_after_output(_):
                deadline = time.monotonic() + 3
                while (work / "java.log").stat().st_size < len(log):
                    if time.monotonic() >= deadline:
                        self.fail("child did not write progress")
                    original_sleep(0.01)
                raise KeyboardInterrupt

            original_sleep = time.sleep
            with patch.object(e1.time, "sleep", side_effect=interrupt_after_output):
                e1.measure_java(work / "manifest.json", result, work, {"limits": []}, None, os.environ)
            self.assertEqual(result["status"], "interrupted")
            self.assertEqual(result["termination_signal"], signal.SIGKILL)
            self.assertEqual(result["latest_progress_percent"], 95.06)
            self.assertEqual(result["estimated_processed_instances"], 2947493)
            self.assertIsNone(result["processed_instances"])
            self.assertEqual((work / "java.log").read_bytes(), log)
            self.assertIn('"latest_progress_percent": 95.06', (work / "resource_monitor.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
