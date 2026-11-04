---
name: ui-regression-check
description: 为 iOS / Xcode 小范围修复选择并运行最小相关 UI 回归（UI regression、UI test），复用有效模拟器构建，区分产品、脚本和环境失败。不替代核心测试或真实外部服务验收。
---

# UI 定向回归

从目标项目读取当前工具识别的 `AGENTS.md`、`CLAUDE.md` 或等价说明及验证约定。本 Skill 负责定向验证，不额外授权修改业务、付费调用、操作用户数据、切换账号或提交推送。

## 先缩小验证范围

* 对照本次 diff 和调用路径，明确目标行为、原有行为及最小可复现场景。能由核心测试覆盖的规则先用核心测试，纯格式改动不单独跑 UI。
* 查找项目已有 UI 测试及启动 helper，优先复用相关用例、fixtures 和测试模式。不能为省时绕过本次需要验证的真实业务入口，也不注入真实凭据。
* 新增测试优先使用稳定的 `accessibilityIdentifier`，其次核对实际存在的标签。等待目标状态，不使用固定睡眠。滚动具体内容区域，仅在目标不可见时滚动。
* 先在一台未被其他任务占用的模拟器跑通相关场景，再按布局或系统差异扩展设备。需要仅验证当前 PR 时，使用固定提交的临时源码副本，保留用户工作区和其他任务的改动。

## 配置执行器模板

[执行脚本](scripts/run_ui_regression.py)及其[行为测试](scripts/test_ui_regression.py)提供 iOS 模拟器定向回归模板。`ExampleApp`、测试名和保留设备名均为虚构占位值，不代表实际项目。将执行器和测试脚本一起复制到目标项目的同一脚本目录，再按现有构建配置替换执行器顶部的设置：

* `PROJECT_FILE`、`BUILD_SETTINGS`：实际 `.xcodeproj`、scheme、configuration、SDK 和签名参数。模板使用 Debug 模拟器本地签名，需要 Keychain 的场景不要关闭签名。
* `TEST_SOURCE`、`TEST_PREFIX`：本次测试类的源码路径及 `测试 target/测试类/` 前缀。源码文件应只包含所选测试类，先核对当前方法名。
* `BUILD_INPUTS`：使用相对目标项目根目录的路径，覆盖 App、依赖、测试、资源、项目声明和锁文件。每项必须存在，路径写错会报错并停止，不能跳过后复用构建。路径存在仍不代表覆盖完整，需按项目实际构建配置核对遗漏。
* `EXPECTED_BINARIES`：相对 DerivedData `Build/Products/` 的 App 和 UI 测试可执行文件路径，与当前构建配置保持一致。
* `PROTECTED_DEVICES`：项目保留或其他验收专用的设备名。使用 `xcrun simctl list devices available` 核对现有设备及占用情况，不操作被保留的设备。

从目标项目根目录运行。下例的脚本路径、设备和用例都需替换：

```bash
python3 Scripts/run_ui_regression.py --device <UDID> --test <testMethod>
```

* `--test` 可重复，只接受配置的测试源码中存在的具体方法。脚本拒绝整套测试、其他测试类及 `testReal...`；其他真实服务用例也需按项目规则排除，不能只依赖命名筛选。
* 先执行 `build-for-testing`，再通过 `.xctestrun` 执行 `test-without-building`。仅在源码位置、配置的构建输入、Xcode／SDK／架构和构建参数一致且产物完整时复用，选择不同用例无需重建。
* `--cache-dir` 指定缓存和结果位置，默认在 `~/Library/Caches/agent-skills/UIRegression/`。`--rebuild` 重新增量构建。`--build-timeout`／`--test-timeout` 默认 1800／600 秒，超时返回 124，不自动重试。
* `--keep-runs N` 按需保留当前源码缓存最近 N 次记录（含本次），默认不清理证据。`.DS_Store` 不属于构建输入，其他未知文件保持保守判断。
* 缓存锁和固定的 `~/Library/Caches/agent-skills/UIRegression/locks/` 设备锁拒绝冲突。子进程继承锁，SIGTERM／超时清理本次进程组。SIGKILL 无法收尾，但存活子进程持锁期间新运行仍被拒绝。
* 锁只协调使用同一锁目录的执行器，仍需避免外部 Xcode 同时操作相同模拟器。报错会给出冲突锁文件路径，可用 `lsof -t <锁文件>` 查询持有该文件的进程，再结合日志判断占用者。被拒绝的新运行不会打印原占用者 PID，不删除锁文件来抢占。

## 失败后定向处理

* 已创建运行目录后，失败路径也写入 `summary.json`，记录 XCTest 摘要及 `runner` 阶段、退出码、源码变化和错误。没有有效 `.xcresult` 时标为 `Unavailable`。SIGKILL 或进程崩溃可能来不及写摘要，此时查看原始日志和存活进程。
* 测试失败保留原退出码，不自动重试。跳过、零执行、数量不足或源码变化不能算通过。即使用例失败，也复核源码并取消已失效的构建缓存。
* 先查看摘要、构建／测试日志和 `.xcresult`，区分前置步骤、脚本、环境及产品断言失败。需要用户认证或设备操作时停在该节点，说明原因。
* 修正前置原因后只重跑受影响用例，不为同一原因反复跑整批，不为让测试通过扩大 App 改动。

## 交付证据

修改模板时先运行 `python3 -B scripts/test_ui_regression.py`（相对本 Skill 目录）。复制并适配后，在目标项目根目录运行 `python3 -B Scripts/test_ui_regression.py`，按实际复制位置替换路径。测试从同目录执行器的配置生成临时项目和产物，不调用 Xcode 或设备，也不修改目标项目数据。之后再用实际模拟器验证首次构建、复用和失败识别，模板测试不替代真实 XCTest。

报告场景、设备／系统、源码版本、构建复用情况、通过／失败／跳过及耗时。原始日志、`.xcresult` 和真实项目配置留在目标项目环境，不回写公开 Skill。区分本轮、历史和未执行的验证。
