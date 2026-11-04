"""Behavior checks for the UI runner; fake builds never invoke Xcode or a device."""
from contextlib import redirect_stderr
import io
import json
import os
import signal
import sys
import time
from pathlib import Path
import subprocess
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_ui_regression as runner


class UIRegressionRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = (Path(temporary.name) / "project").resolve()
        self.cache = Path(temporary.name) / "cache"
        self.directory = self.cache / "runs/fixture"
        self.directory.mkdir(parents=True)
        self.root.mkdir()
        self.input_files = []
        self.input_directories = []
        for name in runner.BUILD_INPUTS:
            path = self.fixture_path(name)
            if path == self.fixture_path(runner.PROJECT_FILE):
                path = path / "project.pbxproj"
            elif not path.suffix:
                self.input_directories.append(path)
                path = path / "fixture.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture-input")
            self.input_files.append(path)
        self.source = self.input_files[0]
        self.test_source = self.fixture_path(runner.TEST_SOURCE)
        self.test_source.parent.mkdir(parents=True, exist_ok=True)
        self.test_source.write_text("func testFirst() {}\nfunc testSecond() {}\nfunc testRealCloud() {}\n")
        for name in runner.EXPECTED_BINARIES:
            self.fixture_path(name, self.cache / "DerivedData/Build/Products")
        locks = patch.object(runner, "DEVICE_LOCK_DIRECTORY", self.cache / "device-locks")
        locks.start()
        self.addCleanup(locks.stop)
        self.tools = ["fixture-toolchain"]
        self.device = "11111111-1111-4111-8111-111111111111"
        self.output = patch("sys.stdout", new_callable=io.StringIO)
        self.output.start()
        self.addCleanup(self.output.stop)

    def fixture_path(self, name, directory=None):
        directory = directory or self.root
        path = (directory / name).resolve()
        path.relative_to(directory.resolve())
        return path

    def build_products(self, *unused):
        products = self.cache / "DerivedData/Build/Products"
        for name in ["fixture.xctestrun", *runner.EXPECTED_BINARIES]:
            path = products / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture-build")

    def build(self, rebuild=False):
        return runner.ensure_build(self.root, self.cache, self.directory, self.tools,
                                   runner.fingerprint(self.root, self.tools), self.device, rebuild)

    def test_first_build_is_reused_until_build_inputs_change(self):
        with patch.object(runner, "logged", side_effect=self.build_products) as command:
            first = self.build()
            self.assertEqual(self.build(), first)
            (self.root / "notes.md").write_text("Unrelated documentation")
            self.assertEqual(self.build(), first)
            self.assertEqual(command.call_count, 1)
            self.source.write_text("struct ChangedScreen {}")
            self.build()
            self.assertEqual(command.call_count, 2)
            args = command.call_args.args[0]
            settings = args.index("-destination") - len(runner.BUILD_SETTINGS)
            self.assertEqual(args[settings:settings + len(runner.BUILD_SETTINGS)], runner.BUILD_SETTINGS)

    def test_sources_tests_resources_dependencies_and_toolchain_invalidate_cache(self):
        initial = runner.fingerprint(self.root, self.tools)
        for path in dict.fromkeys([*self.input_files, self.test_source]):
            with self.subTest(path=str(path.relative_to(self.root))):
                before = path.read_bytes()
                path.write_bytes(before + b" changed")
                self.assertNotEqual(runner.fingerprint(self.root, self.tools), initial)
                path.write_bytes(before)
        self.assertNotEqual(runner.fingerprint(self.root, ["another-toolchain"]), initial)
        other = self.root.parent / "another-project-path"
        shutil.copytree(self.root, other)
        self.assertNotEqual(runner.fingerprint(self.root, self.tools), runner.fingerprint(other, self.tools))

    def test_build_and_personal_xcode_state_do_not_invalidate_cache(self):
        initial = runner.fingerprint(self.root, self.tools)
        for path in [self.source.parent / ".build/cache",
                     self.fixture_path(runner.PROJECT_FILE) / "xcuserdata/person.xcuserstate"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("machine-local state")
        self.assertEqual(runner.fingerprint(self.root, self.tools), initial)

    def test_finder_metadata_is_ignored_but_other_new_inputs_are_conservative(self):
        initial = runner.fingerprint(self.root, self.tools)
        for directory in self.input_directories:
            (directory / ".DS_Store").write_text("Finder metadata")
        self.assertEqual(runner.fingerprint(self.root, self.tools), initial)
        if self.input_directories:
            (self.input_directories[0] / "new-input").write_text("potential build input")
            self.assertNotEqual(runner.fingerprint(self.root, self.tools), initial)

    def test_missing_build_input_is_not_silently_skipped(self):
        for name in ["missing-directory", "missing-file.swift"]:
            with self.subTest(name=name), patch.object(runner, "BUILD_INPUTS", [*runner.BUILD_INPUTS, name]):
                with self.assertRaisesRegex(FileNotFoundError, name):
                    runner.fingerprint(self.root, self.tools)

    def test_empty_build_input_list_is_rejected(self):
        with patch.object(runner, "BUILD_INPUTS", []):
            with self.assertRaisesRegex(ValueError, "BUILD_INPUTS"):
                runner.fingerprint(self.root, self.tools)

    def test_each_input_directory_requires_nonexcluded_files(self):
        empty = self.root / "empty-input"
        empty.mkdir()
        excluded = self.root / "excluded-input"
        (excluded / ".build").mkdir(parents=True)
        (excluded / ".build/cache").write_text("ignored")
        (excluded / ".DS_Store").write_text("ignored")
        for directory in [empty, excluded]:
            with self.subTest(directory=directory.name), \
                    patch.object(runner, "BUILD_INPUTS", [*runner.BUILD_INPUTS, directory.name]):
                with self.assertRaisesRegex(ValueError, directory.name):
                    runner.fingerprint(self.root, self.tools)

    def test_missing_build_input_prevents_reusing_existing_build(self):
        with patch.object(runner, "logged", side_effect=self.build_products):
            self.build()
        args = SimpleNamespace(device=self.device, test=["testFirst"], cache_dir=self.cache, rebuild=False,
                               build_timeout=30, test_timeout=30, keep_runs=None)
        empty = self.root / "empty-input"
        empty.mkdir()
        for inputs in [[*runner.BUILD_INPUTS, "missing-directory"], [], [*runner.BUILD_INPUTS, empty.name]]:
            with self.subTest(inputs=inputs), patch.object(runner, "BUILD_INPUTS", inputs), \
                    patch.object(runner.subprocess, "check_output", side_effect=self.tool_output), \
                    patch.object(runner, "ensure_build") as build:
                with self.assertRaises((FileNotFoundError, ValueError)):
                    runner.run(self.root, args)
                build.assert_not_called()
        self.assertFalse(list((self.cache / "runs").glob("*/summary.json")))

    def test_missing_test_source_reports_configuration_hint_without_invoking_xcode(self):
        self.test_source.unlink()
        argv = ["run_ui_regression.py", "--device", self.device, "--test", "testFirst"]
        errors = io.StringIO()
        with patch.object(runner.sys, "argv", argv), patch.object(runner.Path, "cwd", return_value=self.root), \
                patch.object(runner.subprocess, "check_output") as command, redirect_stderr(errors):
            self.assertEqual(runner.main(), 2)
        self.assertIn("SKILL.md", errors.getvalue())
        self.assertIn(runner.TEST_SOURCE, errors.getvalue())
        command.assert_not_called()

    def test_failed_forced_rebuild_cannot_reuse_earlier_manifest(self):
        with patch.object(runner, "logged", side_effect=self.build_products):
            self.build()
        with patch.object(runner, "logged", side_effect=subprocess.CalledProcessError(65, ["xcodebuild"])) as command:
            with self.assertRaises(subprocess.CalledProcessError):
                self.build(rebuild=True)
            self.assertEqual(command.call_count, 1)
        self.assertFalse((self.cache / "build.json").exists())

    def test_changing_source_during_build_never_marks_build_reusable(self):
        def changed_build(*args):
            self.build_products()
            self.source.write_text("changed during build")
        with patch.object(runner, "logged", side_effect=changed_build):
            with self.assertRaisesRegex(RuntimeError, "构建期间源码发生变化"):
                self.build()
        self.assertFalse((self.cache / "build.json").exists())

    def test_deleted_product_requires_new_build(self):
        with patch.object(runner, "logged", side_effect=self.build_products) as command:
            self.build()
            (self.cache / "DerivedData/Build/Products" / runner.EXPECTED_BINARIES[0]).unlink()
            self.build()
            self.assertEqual(command.call_count, 2)

    def test_unknown_wildcard_and_real_service_tests_are_rejected(self):
        self.assertEqual(runner.selected_tests(self.root, ["testFirst", runner.TEST_PREFIX + "testFirst"]), [runner.TEST_PREFIX + "testFirst"])
        for name in ["testMissing", runner.TEST_PREFIX.rstrip("/"), "*", "testRealCloud", "OtherTarget/OtherClass/testFirst"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                runner.selected_tests(self.root, [name])

    def test_zero_skipped_missing_or_failed_tests_never_count_as_passed(self):
        valid = dict(result="Passed", passedTests=2, failedTests=0, skippedTests=0, totalTestCount=2)
        runner.check_summary(valid, 2)
        for updates in [dict(passedTests=0, totalTestCount=0), dict(passedTests=1, skippedTests=1),
                        dict(passedTests=1, totalTestCount=1), dict(failedTests=1), dict(result="Failed")]:
            with self.subTest(updates=updates), self.assertRaises(RuntimeError):
                runner.check_summary({**valid, **updates}, 2)

    def test_concurrent_cache_or_device_use_fails_without_waiting(self):
        path = self.cache / "lease.lock"
        with runner.lease(path):
            with self.assertRaisesRegex(RuntimeError, "另一个定向回归"):
                with runner.lease(path):
                    self.fail("A competing runner entered the lease")
        with runner.lease(path):
            pass

    def test_runner_reuses_build_for_different_test_selections(self):
        commands = []
        def output(command, **unused):
            if command[:3] == ["xcrun", "simctl", "list"]:
                return json.dumps({"devices": {"fixture": [dict(udid=self.device, name="Fixture iPhone", state="Booted")]}})
            if "xcresulttool" in command:
                return json.dumps(dict(result="Passed", passedTests=1, failedTests=0, skippedTests=0, totalTestCount=1))
            return "fixture-toolchain"
        def execute(command, path, *unused):
            commands.append(command)
            if "build-for-testing" in command:
                self.build_products()
            elif "test-without-building" in command:
                Path(command[command.index("-resultBundlePath") + 1]).mkdir()
            elif "xcresulttool" in command:
                path.write_text(json.dumps(dict(result="Passed", passedTests=1, failedTests=0,
                                                skippedTests=0, totalTestCount=1)))
        args = SimpleNamespace(device=self.device, test=["testFirst"], cache_dir=self.cache, rebuild=False,
                               build_timeout=runner.BUILD_TIMEOUT, test_timeout=runner.TEST_TIMEOUT, keep_runs=None)
        with patch.object(runner.subprocess, "check_output", side_effect=output), patch.object(runner, "logged", side_effect=execute), \
                patch.object(runner, "DEVICE_LOCK_DIRECTORY", self.cache / "device-locks"):
            runner.run(self.root, args)
            args.test = ["testSecond"]
            runner.run(self.root, args)
        self.assertEqual(sum("build-for-testing" in command for command in commands), 1)
        tests = [command for command in commands if "test-without-building" in command]
        self.assertEqual(len(tests), 2)
        self.assertIn("-only-testing:" + runner.TEST_PREFIX + "testSecond", tests[1])
        self.assertIn("-xctestrun", tests[1])
        self.assertNotIn("-project", tests[1])

    def test_reserved_device_is_rejected_before_build_or_boot(self):
        args = SimpleNamespace(device=self.device, test=["testFirst"], cache_dir=self.cache, rebuild=False,
                               build_timeout=runner.BUILD_TIMEOUT, test_timeout=runner.TEST_TIMEOUT, keep_runs=None)
        reserved = next(iter(runner.PROTECTED_DEVICES), "Fixture Reserved Device")
        devices = {"devices": {"fixture": [dict(udid=self.device, name=reserved, state="Shutdown")]}}
        with patch.object(runner.subprocess, "check_output", return_value=json.dumps(devices)) as output, \
                patch.object(runner, "PROTECTED_DEVICES", {reserved}), patch.object(runner, "logged") as command:
            with self.assertRaisesRegex(ValueError, "未被项目保留的模拟器"):
                runner.run(self.root, args)
            self.assertEqual(output.call_count, 1)
            command.assert_not_called()

    def tool_output(self, command, **unused):
        if command[:3] == ["xcrun", "simctl", "list"]:
            return json.dumps({"devices": {"fixture": [dict(udid=self.device, name="Fixture iPhone", state="Shutdown")]}})
        return "fixture-toolchain"

    def real_command_fixtures(self, change_source=False):
        tools = self.root.parent / "bin"
        tools.mkdir()
        script = tools / "fixture-tool"
        script.write_text("#!" + sys.executable + "\n" + '''import json, os, sys
from pathlib import Path
root = Path(os.environ["UI_FIXTURE_ROOT"])
cache = Path(os.environ["UI_FIXTURE_CACHE"])
with (root / "commands.log").open("a") as out:
    out.write(Path(sys.argv[0]).name + " " + " ".join(sys.argv[1:]) + "\\n")
if "build-for-testing" in sys.argv:
    products = cache / "DerivedData/Build/Products"
    for name in ["fixture.xctestrun", *json.loads(os.environ["UI_FIXTURE_BINARIES"])]:
        path = products / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("build")
elif "test-without-building" in sys.argv:
    Path(sys.argv[sys.argv.index("-resultBundlePath") + 1]).mkdir()
    if os.environ["UI_FIXTURE_CHANGE"] == "1":
        Path(os.environ["UI_FIXTURE_SOURCE"]).write_text("changed during failing test")
    print("fixture XCTest failure")
    sys.exit(65)
elif "xcresulttool" in sys.argv:
    print(json.dumps(dict(result="Failed", passedTests=0, failedTests=1, skippedTests=0, totalTestCount=1)))
''')
        script.chmod(0o755)
        for name in ["xcodebuild", "xcrun"]:
            (tools / name).symlink_to(script)
        environment = patch.dict(os.environ, {
            "PATH": str(tools) + os.pathsep + os.environ["PATH"],
            "UI_FIXTURE_ROOT": str(self.root), "UI_FIXTURE_CACHE": str(self.cache),
            "UI_FIXTURE_CHANGE": "1" if change_source else "0",
            "UI_FIXTURE_SOURCE": str(self.source),
            "UI_FIXTURE_BINARIES": json.dumps(runner.EXPECTED_BINARIES),
        })
        environment.start()
        self.addCleanup(environment.stop)

    def test_real_logged_failure_writes_xctest_summary_and_preserves_exit_code(self):
        self.real_command_fixtures()
        args = SimpleNamespace(device=self.device, test=["testFirst"], cache_dir=self.cache, rebuild=False,
                               build_timeout=30, test_timeout=30, keep_runs=None)
        with patch.object(runner.subprocess, "check_output", side_effect=self.tool_output), redirect_stderr(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                runner.run(self.root, args)
        self.assertEqual(raised.exception.returncode, 65)
        summary = json.loads(next((self.cache / "runs").glob("*/summary.json")).read_text())
        self.assertEqual(summary["failedTests"], 1)
        self.assertEqual(summary["runner"]["exitCode"], 65)
        self.assertFalse(summary["runner"]["sourceChanged"])
        commands = (self.root / "commands.log").read_text()
        self.assertEqual(commands.count("test-without-building"), 1)
        self.assertIn("simctl bootstatus", commands)
        self.assertNotIn("simctl boot ", commands)

    def test_real_logged_failure_still_invalidates_changed_sources(self):
        self.real_command_fixtures(change_source=True)
        args = SimpleNamespace(device=self.device, test=["testFirst"], cache_dir=self.cache, rebuild=False,
                               build_timeout=30, test_timeout=30, keep_runs=None)
        with patch.object(runner.subprocess, "check_output", side_effect=self.tool_output), redirect_stderr(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                runner.run(self.root, args)
        self.assertEqual(raised.exception.returncode, 65)
        summary = json.loads(next((self.cache / "runs").glob("*/summary.json")).read_text())
        self.assertTrue(summary["runner"]["sourceChanged"])
        self.assertEqual(summary["runner"]["exitCode"], 65)
        self.assertFalse((self.cache / "build.json").exists())

    def test_empty_input_during_failure_still_writes_summary_and_preserves_exit_code(self):
        directory = self.root / "disappearing-input"
        directory.mkdir()
        source = directory / "fixture.txt"
        source.write_text("input")
        args = SimpleNamespace(device=self.device, test=["testFirst"], cache_dir=self.cache, rebuild=False,
                               build_timeout=30, test_timeout=30, keep_runs=None)

        def execute(command, *unused):
            if "build-for-testing" in command:
                self.build_products()
            elif "test-without-building" in command:
                source.unlink()
                raise subprocess.CalledProcessError(65, command)

        with patch.object(runner, "BUILD_INPUTS", [*runner.BUILD_INPUTS, directory.name]), \
                patch.object(runner.subprocess, "check_output", side_effect=self.tool_output), \
                patch.object(runner, "logged", side_effect=execute), redirect_stderr(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                runner.run(self.root, args)
        self.assertEqual(raised.exception.returncode, 65)
        summary = json.loads(next((self.cache / "runs").glob("*/summary.json")).read_text())
        self.assertEqual(summary["runner"]["exitCode"], 65)
        self.assertIsNone(summary["runner"]["sourceChanged"])
        self.assertIn(directory.name, summary["runner"]["sourceCheckError"])
        self.assertFalse((self.cache / "build.json").exists())

    def test_device_lease_is_shared_across_cache_and_temp_directories(self):
        runner.DEVICE_LOCK_DIRECTORY.mkdir()
        with runner.lease(runner.DEVICE_LOCK_DIRECTORY / (self.device.upper() + ".lock")):
            for name in ["one", "two"]:
                args = SimpleNamespace(device=self.device, test=["testFirst"], cache_dir=self.cache / name,
                                       rebuild=False, build_timeout=30, test_timeout=30, keep_runs=None)
                with patch.dict(os.environ, {"TMPDIR": str(self.root.parent / name)}), \
                        patch.object(runner.subprocess, "check_output", side_effect=self.tool_output), \
                        patch.object(runner, "ensure_build") as build:
                    with self.assertRaisesRegex(RuntimeError, "另一个定向回归"):
                        runner.run(self.root, args)
                    build.assert_not_called()

    def test_opt_in_pruning_preserves_current_run_and_unrelated_entries(self):
        names = [f"20260101-00000{i}-12345678" for i in range(3)]
        for i, name in enumerate(names):
            path = self.cache / "runs" / name
            path.mkdir()
            os.utime(path, (i + 1, i + 1))
        current = self.cache / "runs/20260101-000009-12345678"
        current.mkdir()
        runner.prune_runs(self.cache, current, None)
        self.assertTrue(all((self.cache / "runs" / name).exists() for name in names))
        runner.prune_runs(self.cache, current, 2)
        self.assertTrue(current.exists())
        self.assertTrue((self.cache / "runs" / names[-1]).exists())
        self.assertFalse((self.cache / "runs" / names[0]).exists())
        self.assertTrue(self.directory.exists())

    def test_main_uses_invoking_project_root_instead_of_skill_directory(self):
        argv = ["run_ui_regression.py", "--device", self.device, "--test", "testFirst"]
        with patch.object(runner.sys, "argv", argv), patch.object(runner.Path, "cwd", return_value=self.root), \
                patch.object(runner, "run") as run:
            self.assertEqual(runner.main(), 0)
        self.assertEqual(run.call_args.args[0], self.root)

    def test_main_preserves_test_failure_exit_code_without_retry(self):
        argv = ["run_ui_regression.py", "--device", self.device, "--test", "testFirst"]
        with patch.object(runner.sys, "argv", argv), patch.object(runner, "run", side_effect=subprocess.CalledProcessError(65, ["xcodebuild"])) as run, \
                redirect_stderr(io.StringIO()):
            self.assertEqual(runner.main(), 65)
            self.assertEqual(run.call_count, 1)


class ProcessLeaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.lock = self.root / "device.lock"

    def wait_for(self, path):
        deadline = time.monotonic() + 5
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(path.exists(), "Fixture process did not reach its ready point")

    def terminate_group(self, pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def launch(self):
        child = self.root / "child.py"
        child.write_text('''import os, subprocess, sys, time
from pathlib import Path
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], close_fds=False)
Path(sys.argv[1] + ".grandchild").write_text(str(grandchild.pid))
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(60)
''')
        helper = self.root / "helper.py"
        helper.write_text('''import signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import run_ui_regression as runner
signal.signal(signal.SIGTERM, runner.interrupted)
root = Path(sys.argv[2])
with runner.lease(root / "device.lock") as fd:
    runner.logged([sys.executable, str(root / "child.py"), str(root / "child.pid")],
                  root / "command.log", root, (fd,), 60)
''')
        with (self.root / "helper.log").open("w") as output:
            parent = subprocess.Popen([sys.executable, str(helper), str(Path(runner.__file__).parent), str(self.root)],
                                      stdout=output, stderr=subprocess.STDOUT)
        self.addCleanup(lambda: parent.kill() if parent.poll() is None else None)
        self.wait_for(self.root / "child.pid")
        child_pid = int((self.root / "child.pid").read_text())
        self.addCleanup(self.terminate_group, child_pid)
        return parent, child_pid

    def test_sigkill_parent_keeps_child_lease_until_child_exits(self):
        parent, child_pid = self.launch()
        parent.kill()
        parent.wait(timeout=5)
        os.kill(child_pid, 0)
        with self.assertRaisesRegex(RuntimeError, "另一个定向回归"):
            with runner.lease(self.lock):
                self.fail("Lease was released while the child was still alive")
        self.terminate_group(child_pid)
        deadline = time.monotonic() + 5
        while True:
            try:
                with runner.lease(self.lock):
                    break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    self.fail("Lease remained held after the child was killed")
                time.sleep(0.01)

    def test_sigterm_parent_terminates_command_group_and_releases_lease(self):
        parent, unused_child_pid = self.launch()
        parent.terminate()
        self.assertEqual(parent.wait(timeout=5), 143)
        with runner.lease(self.lock):
            pass

    def test_timeout_terminates_command_and_inherited_lease(self):
        command = [sys.executable, "-c", "import subprocess, sys, time; "
                   "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], close_fds=False); time.sleep(60)"]
        with runner.lease(self.lock) as fd:
            with redirect_stderr(io.StringIO()), patch("sys.stdout", new_callable=io.StringIO):
                with self.assertRaises(subprocess.TimeoutExpired):
                    runner.logged(command, self.root / "timeout.log", self.root, (fd,), 0.1)
        with runner.lease(self.lock):
            pass


if __name__ == "__main__":
    unittest.main()
