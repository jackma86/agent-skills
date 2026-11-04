# Git 检查范围

执行 Git 自检或 PR 审查的空白检查时读取。`task-base` 是任务开始时记录的提交或当前 PR 的实际比较基线，`head` 是本次审查或交付的提交。

| 范围 | 检查 |
| --- | --- |
| 未暂存 | `git diff --check` |
| 已暂存 | `git diff --cached --check` |
| 本次已提交 | `git diff --check <task-base> <head>` |
| 本次未跟踪文本文件 | 逐个执行 `git diff --no-index --check /dev/null <file>` |

暂存内容与工作区互相抵消时，`git diff --check HEAD` 也不能代替暂存区检查。新仓库没有 `HEAD` 时使用暂存区检查，不引用不存在的提交。

检查未信任候选时，从可信控制目录固定基线属性：`git --attr-source=<task-base> diff --check <task-base> <head>`。先执行 `git --attr-source=<task-base> rev-parse --verify <task-base>^{tree}` 探测当前 Git 的能力和基线有效性。失败时记录版本与 stderr，将该检查标为未完成，不静默使用候选属性。控制仓库的 `info/attributes`、Git 配置及外部属性来源也须可信。

`--no-index` 先确认文件存在、可读且属于当前任务，再联合检查退出码、stdout 和 stderr。当前常见结果：

* 干净新文件，包括空文件，退出 1 且无诊断。
* 空白问题退出 3，stdout 有空白诊断。
* 路径不存在也可能退出 1，但 stderr 有错误。

不凭退出码或空文件类型单独判断通过，无法解释的诊断按检查未完成处理。保留实际结果，不把较早代码状态的检查当成当前版本结果。
