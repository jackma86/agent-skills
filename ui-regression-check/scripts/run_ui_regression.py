#!/usr/bin/env python3
"""Run explicitly selected, isolated Daynest UI tests with a validated simulator build."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import shutil
import subprocess
import sys
import time
import uuid


BUILD_SETTINGS = ["-scheme", "Daynest", "-configuration", "Debug", "-sdk", "iphonesimulator",
                  "CODE_SIGN_IDENTITY=-", "CODE_SIGNING_ALLOWED=YES"]
BUILD_INPUTS = ["App", "Packages", "Tests", "Daynest.xcodeproj", "project.yml"]
EXCLUDED_DIRECTORIES = {".build", ".git", "DerivedData", "xcuserdata", "__pycache__"}
EXCLUDED_FILES = {".DS_Store"}
CACHE_ROOT = Path.home() / "Library/Caches/Daynest/UIRegression"
DEVICE_LOCK_DIRECTORY = CACHE_ROOT / "locks"
BUILD_TIMEOUT = 1800
TEST_TIMEOUT = 600
PROTECTED_DEVICES = {"Daynest Sync iPhone", "Daynest Sync iPad"}
TEST_PREFIX = "DaynestUITests/DaynestUITests/"


def selected_tests(root, names):
    source = (root / "Tests/DaynestUITests/DaynestUITests.swift").read_text()
    available = set(re.findall(r"^\s*func (test\w+)\(", source, re.MULTILINE))
    result = []
    for name in names:
        method = name.removeprefix(TEST_PREFIX)
        if method not in available or method.startswith("testReal"):
            raise ValueError(f"不可运行未知用例、整套测试或真实云端测试：{name}")
        target = TEST_PREFIX + method
        if target not in result:
            result.append(target)
    return result


def fingerprint(root, toolchain):
    digest = hashlib.sha256(json.dumps([str(root), toolchain, BUILD_SETTINGS], sort_keys=True).encode())
    files = []
    for name in BUILD_INPUTS:
        path = root / name
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for directory, children, names in os.walk(path):
                children[:] = [name for name in children if name not in EXCLUDED_DIRECTORIES]
                files.extend(Path(directory) / name for name in names
                             if name not in EXCLUDED_FILES and not name.endswith(".xcuserstate"))
    for path in sorted(files):
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


@contextmanager
def lease(path):
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"另一个定向回归正在使用此构建或设备：{path}") from error
        # Closing our descriptor must leave inherited child leases in force.
        yield handle.fileno()


def interrupted(signum, unused_frame):
    raise SystemExit(128 + signum)


def stop_process_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def logged(command, path, root, lock_fds=(), timeout=120):
    print(f"[RUN] {' '.join(map(str, command))}\n[LOG] {path}", flush=True)
    with path.open("w") as output:
        process = subprocess.Popen(command, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True, pass_fds=lock_fds)
        print(f"[PID] {process.pid}", flush=True)
        try:
            process.wait(timeout=timeout)
        except BaseException:
            stop_process_group(process)
            raise
        stop_process_group(process)
    if process.returncode:
        print("\n".join(path.read_text(errors="replace").splitlines()[-24:]), file=sys.stderr)
        raise subprocess.CalledProcessError(process.returncode, command)


def ensure_build(root, cache, run_directory, tools, before, device, rebuild=False,
                 lock_fds=(), timeout=BUILD_TIMEOUT):
    manifest = cache / "build.json"
    derived = cache / "DerivedData"
    products = derived / "Build/Products/Debug-iphonesimulator"
    metadata = json.loads(manifest.read_text()) if manifest.exists() else {}
    test_run = cache / metadata.get("xctestrun", "missing")
    binaries = [products / "Daynest.app/Daynest", products / "DaynestUITests-Runner.app/PlugIns/DaynestUITests.xctest/DaynestUITests"]
    if not rebuild and metadata.get("fingerprint") == before and test_run.is_file() and all(p.is_file() for p in binaries):
        print(f"[REUSE] 构建 {before[:12]}", flush=True)
        return test_run
    # A failed forced rebuild must not leave the earlier build eligible for reuse.
    manifest.unlink(missing_ok=True)
    print(f"[BUILD] 构建 {before[:12]}", flush=True)
    logged(["xcodebuild", "build-for-testing", "-project", str(root / "Daynest.xcodeproj"),
            *BUILD_SETTINGS, "-destination", f"platform=iOS Simulator,id={device}",
            "-derivedDataPath", str(derived)], run_directory / "build.log", root, lock_fds, timeout)
    if fingerprint(root, tools) != before:
        raise RuntimeError("构建期间源码发生变化，本次构建不进入复用缓存。")
    candidates = list((derived / "Build/Products").glob("*.xctestrun"))
    if not candidates or not all(p.is_file() for p in binaries):
        raise RuntimeError("构建未生成完整 App、UI 测试程序或 xctestrun，不能继续测试。")
    test_run = max(candidates, key=lambda p: p.stat().st_mtime_ns)
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps({"fingerprint": before, "xctestrun": str(test_run.relative_to(cache))}, indent=2) + "\n")
    temporary.replace(manifest)
    return test_run


def check_summary(summary, count):
    if summary.get("result") != "Passed" or summary.get("passedTests") != count or summary.get("failedTests") != 0 \
            or summary.get("skippedTests") != 0 or summary.get("totalTestCount") != count:
        counts = {name: summary.get(name) for name in ["result", "passedTests", "failedTests", "skippedTests", "totalTestCount"]}
        raise RuntimeError(f"定向回归未完整通过，零执行、跳过或缺失用例不能计为成功：{json.dumps(counts, ensure_ascii=False)}")


def read_summary(result, directory, root, lock_fds):
    try:
        if not result.exists():
            raise ValueError("当前阶段没有生成 xcresult，无法取得 XCTest 摘要。")
        path = directory / "summary.log"
        logged(["xcrun", "xcresulttool", "get", "test-results", "summary", "--path", str(result)],
               path, root, lock_fds, 60)
        return json.loads(path.read_text())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"result": "Unavailable", "summaryError": str(error)}


def prune_runs(cache, current, keep):
    if keep is None:
        return
    previous = [path for path in (cache / "runs").iterdir()
                if path != current and path.is_dir() and not path.is_symlink()
                and re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{8}", path.name)]
    for path in sorted(previous, key=lambda p: p.stat().st_mtime_ns, reverse=True)[keep - 1:]:
        shutil.rmtree(path)
        print(f"[PRUNE] {path}", flush=True)


def run(root, args):
    if args.build_timeout <= 0 or args.test_timeout <= 0:
        raise ValueError("构建和测试超时必须大于 0 秒。")
    if args.keep_runs is not None and args.keep_runs < 1:
        raise ValueError("保留的运行记录数必须至少为 1。")
    targets = selected_tests(root, args.test)
    device_id = str(uuid.UUID(args.device)).upper()
    devices = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "--json"], text=True))
    device = next((d for values in devices["devices"].values() for d in values if d["udid"].upper() == device_id), None)
    if device is None or device["name"] in PROTECTED_DEVICES:
        raise ValueError("请选择已存在的非同步验收模拟器，不创建、抹掉或操作 Daynest Sync 测试对。")
    tools = [platform.machine(), subprocess.check_output(["xcode-select", "-p"], text=True),
             subprocess.check_output(["xcodebuild", "-version"], text=True),
             subprocess.check_output(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-version", "--show-sdk-build-version"], text=True)]
    cache = (args.cache_dir or CACHE_ROOT / hashlib.sha256(str(root).encode()).hexdigest()[:12]).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    DEVICE_LOCK_DIRECTORY.mkdir(parents=True, exist_ok=True)
    device_lock = DEVICE_LOCK_DIRECTORY / f"{device_id}.lock"
    with lease(cache / "run.lock") as cache_fd, lease(device_lock) as device_fd:
        lock_fds = (cache_fd, device_fd)
        started = time.monotonic()
        directory = cache / "runs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        directory.mkdir(parents=True)
        print(f"[DEVICE] {device['name']} ({device_id})\n[ARTIFACTS] {directory}", flush=True)
        before = fingerprint(root, tools)
        result = directory / "Test.xcresult"
        summary = None
        failure = None
        phase = "prepare"
        try:
            prune_runs(cache, directory, args.keep_runs)
            phase = "build"
            test_run = ensure_build(root, cache, directory, tools, before, device_id, args.rebuild,
                                    lock_fds, args.build_timeout)
            phase = "boot"
            logged(["xcrun", "simctl", "bootstatus", device_id, "-b"],
                   directory / "boot-status.log", root, lock_fds, 180)
            phase = "test"
            logged(["xcodebuild", "test-without-building", "-xctestrun", str(test_run),
                    "-destination", f"platform=iOS Simulator,id={device_id}", "-parallel-testing-enabled", "NO",
                    "-resultBundlePath", str(result), *["-only-testing:" + target for target in targets]],
                   directory / "test.log", root, lock_fds, args.test_timeout)
            phase = "summary"
            summary = read_summary(result, directory, root, lock_fds)
            check_summary(summary, len(targets))
        except BaseException as error:
            failure = error
            raise
        finally:
            source_error = None
            try:
                changed = fingerprint(root, tools) != before
            except OSError as error:
                changed = None
                source_error = str(error)
            if changed is not False:
                (cache / "build.json").unlink(missing_ok=True)
                print("[INVALID] 源码已变化或无法复核，本轮结果不能验证当前源码，已取消构建复用。", file=sys.stderr)
            if summary is None:
                summary = ({"result": "Unavailable"} if isinstance(failure, (SystemExit, KeyboardInterrupt))
                           else read_summary(result, directory, root, lock_fds))
            if isinstance(failure, subprocess.CalledProcessError):
                exit_code = failure.returncode
            elif isinstance(failure, subprocess.TimeoutExpired):
                exit_code = 124
            elif isinstance(failure, SystemExit):
                exit_code = failure.code
            else:
                exit_code = 2 if failure or changed is not False else 0
            summary["runner"] = {"phase": phase, "exitCode": exit_code,
                                 "error": str(failure) if failure else None,
                                 "sourceFingerprint": before, "sourceChanged": changed,
                                 "sourceCheckError": source_error, "tests": targets,
                                 "durationSeconds": round(time.monotonic() - started, 1)}
            (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
            if failure is None and changed is not False:
                raise RuntimeError("构建或测试期间源码发生变化或无法复核，本轮结果已作废。")
        print(f"[PASS] {len(targets)} 项通过，耗时 {time.monotonic() - started:.1f}s；源码 {before[:12]}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="现有非同步验收模拟器的 UDID")
    parser.add_argument("--test", action="append", required=True, help="完整用例方法名或 DaynestUITests/DaynestUITests/test...，可重复指定")
    parser.add_argument("--cache-dir", type=Path, help="构建缓存及原始日志目录，默认位于本机 Library/Caches")
    parser.add_argument("--rebuild", action="store_true", help="主动重新增量构建，不清空 DerivedData")
    parser.add_argument("--build-timeout", type=int, default=BUILD_TIMEOUT, help="构建超时秒数，默认 1800")
    parser.add_argument("--test-timeout", type=int, default=TEST_TIMEOUT, help="测试超时秒数，默认 600")
    parser.add_argument("--keep-runs", type=int, help="按需清理当前源码缓存的旧运行记录，保留最近 N 次（含本次），默认不清理")
    args = parser.parse_args()
    handlers = {number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        run(Path(__file__).resolve().parents[1], args)
    except subprocess.TimeoutExpired as error:
        print(f"[FAIL] 命令超过 {error.timeout} 秒，已终止本次进程组，不自动重试。", file=sys.stderr)
        return 124
    except subprocess.CalledProcessError as error:
        print(f"[FAIL] 命令退出 {error.returncode}；先检查对应日志，不自动重试。", file=sys.stderr)
        return error.returncode if error.returncode > 0 else 1
    except (ValueError, OSError, RuntimeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 2
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
    return 0


if __name__ == "__main__":
    sys.exit(main())
