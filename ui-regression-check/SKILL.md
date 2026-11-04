---
name: ui-regression-check
description: 为 Daynest 小范围修复选择并运行最小相关 UI 回归（UI regression、UI test），复用有效模拟器构建，区分产品、脚本和环境失败。不替代核心测试、真实 AI 或双端 iCloud 验收。
---

# Daynest UI 定向回归

项目规则来自 Daynest 根目录的 `AGENTS.md`，代码修改仍遵循项目内的 `.agents/skills/code-change-check/SKILL.md`。本 Skill 负责定向验证，不额外授权修改业务、付费调用、操作正常账本、切换账号或提交推送。

## 保存副本说明

* 本目录保存 Daynest 项目版 Skill，以及 `scripts/` 中的执行器和测试副本。
* 实际回归在 Daynest 仓库根目录运行文中的 `Scripts/...` 命令。Claude Code 项目入口也指向 Daynest 内的正式目录。
* 执行器依赖 Daynest 的目录关系，不在本存档目录直接运行。同步修订时同时核对正式版和本目录的脚本，保留项目版说明。

## 先缩小验证范围

* 对照本次 diff 和调用路径，说明目标行为、原有行为及最小可复现场景。数据库规则先用核心测试，纯格式改动不单独跑 UI。
* 查找 `Tests/DaynestUITests/DaynestUITests.swift` 中现有方法，优先复用相关用例。先在一台非同步验收模拟器跑通新增或修改的场景，再按分栏、系统差异等实际风险扩展设备。不默认覆盖所有语言、外观和系统。
* 复用 `launchApp`、`DAYNEST_UI_TEST_SESSION`、现有 fixtures 和 `--fake-ai-test`。非配置场景可复用已有预置状态，不能为省时绕过本次需要验证的真实业务入口。当前需要配置 AI 的用例仍使用虚构 Key 与模型选择 helper，脚本不会读取或注入真实凭据。
* 新增测试优先稳定的 `accessibilityIdentifier`，其次核对实际存在的标签。等待目标状态，不使用固定睡眠。滚动具体内容区域，仅在目标不可见时滚动，避免误关 Sheet。
* 多人或多 Agent 工作时先核对工作区，不能把他人的未提交功能带入本次提交。需要验证仅属于当前 PR 的内容时，使用该提交的临时源码副本并复制本次文件，保留原工作区。

## 统一执行入口

从仓库根目录使用[执行脚本](scripts/run_ui_regression.py)，先用 `xcrun simctl list devices available` 选现有设备。不要使用或抹掉 `Daynest Sync iPhone`／`Daynest Sync iPad`。

```bash
python3 Scripts/run_ui_regression.py --device <UDID> \
  --test testManualExpensePersistsAfterRelaunch
```

* `--test` 可重复，只接受 `DaynestUITests` 类中存在的具体方法。脚本不接受整套测试、`testReal...` 或真实 API 测试类。方法可能随功能修改而改名，先读取当前源码，不照抄历史命令。
* `--cache-dir <目录>` 可指定缓存和原始结果位置。默认使用本机 `Library/Caches/Daynest/UIRegression`，不进入仓库。`--rebuild` 强制重新增量构建，不清空缓存目录。
* `--build-timeout`、`--test-timeout` 分别控制构建和测试秒数，默认 1800／600，超时返回 124，不自动重试。`--keep-runs N` 按需清理当前源码缓存的旧运行目录，保留最近 N 次（含本次），默认保留证据不自动删除。
* 脚本用模拟器本地签名执行 `build-for-testing`，再通过生成的 `.xctestrun` 运行 `test-without-building`，避免反复解析项目依赖。不得关闭签名来加速需要 Keychain 的场景。
* 仅当源码位置、App／核心包／UI 测试／资源／项目及依赖声明、Xcode／SDK／架构和构建参数一致，且产物完整时复用。选择不同用例无需重建，修改测试本身则重新构建。
* 构建或测试期间源码变化时停止认定当前版本通过，即使用例失败也复核源码并取消构建复用。Finder 的 `.DS_Store` 不属于构建输入，其他未知文件保持保守判断。
* 缓存锁和固定的 `~/Library/Caches/Daynest/UIRegression/locks/` 设备锁拒绝冲突，设备锁不随 `TMPDIR` 或 `--cache-dir` 改变。子进程继承锁，SIGTERM／超时清理本次进程组。SIGKILL 无法收尾，但存活子进程持锁期间新运行仍被拒绝。
* 锁只协调本脚本，仍需避免外部 Xcode 等工具同时操作相同模拟器。遇到锁冲突先检查原始日志和打印的 PID，不删除锁文件来抢占。

## 失败后定向处理

* 已创建运行目录后，失败路径也写入 `summary.json`，记录 XCTest 摘要及 `runner` 的阶段、退出码、源码变化和错误。没有有效 `.xcresult` 时明确标为 `Unavailable`。SIGKILL 或进程崩溃可能来不及写摘要，此时查看原始日志和存活进程。
* 先查看 `summary.json`、`build.log`／`test.log` 和 `.xcresult`，构建失败、Keychain／系统权限、错误定位与产品断言分开判断。
* 前置步骤未完成时，不能称为产品复现失败。先修正前置原因，只重跑受影响的用例，不为同一原因反复重跑整批或增加等待。
* 测试失败保留原退出码，不自动重试。跳过、零执行、数量不足或源码变化返回失败，不冒充通过。需要用户认证或设备操作时停在该节点，明确说明原因。
* 若故障实际属于测试脚本或运行环境，不为让测试通过扩大 App 改动。测试中有并发修改、无法归因或超出小范围时，说明继续验证的必要性再调整范围。

## 交付证据

维护执行器时先运行 `python3 -B Scripts/test_ui_regression.py`，再用实际模拟器验证首次构建、复用和失败识别。脚本单元测试不替代实际 XCTest 执行。

简短报告所测场景、设备／系统、对应源码、构建是否复用、实际通过／失败／跳过及耗时。保留脚本打印的原始日志与 `.xcresult`，不另外生成长检查文档。区分本轮结果、历史结果和未执行范围，不把结构校验当作实际流程已验证。
