# Agent Skills

简体中文 | [English](README.en.md)

面向 coding agent 的开发工作流技能集，整理代码修改、自检、fork 上游同步和版本发布中的可复用流程。

每个 Skill 以独立的 `SKILL.md` 提供指令，不绑定具体项目、账号或技术栈。项目规则由目标仓库的 `AGENTS.md` 和贡献规范定义。

## 技能索引

| Skill | 用途 | 适用场景 |
| --- | --- | --- |
| [code-change-check](code-change-check/SKILL.md) | 追踪调用路径，选择最小完整改动，结合完整 diff 自检并验证 | 修复、功能调整、重构 |
| [fork-upstream-sync](fork-upstream-sync/SKILL.md) | 识别上下游，保留 fork 定制，同步上游并发布可追溯的自有 tag | fork 状态检查、上游合并、正式 tag 或分支快照发布 |

## 目录结构

```text
agent-skills/
├── .gitignore
├── LICENSE
├── README.md
├── README.en.md
├── code-change-check/
│   └── SKILL.md
└── fork-upstream-sync/
    └── SKILL.md
```

## 安装与使用

将所需 Skill 的完整子目录放入所用工具支持的技能目录，保留目录名与 `SKILL.md`。安装位置和调用方式以对应工具的文档为准。

### Codex

按 [Codex 官方说明](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)，可以选择以下位置：

* 个人使用：`~/.agents/skills/<skill-name>/SKILL.md`。
* 项目共享：目标项目的 `.agents/skills/<skill-name>/SKILL.md`。

只复制需要的技能子目录，例如 `code-change-check/`，无需把整个仓库放入技能目录。目标位置已有同名 Skill 时，先比较内容再决定是否更新。

安装后，在目标项目的聊天中显式调用：

```text
$code-change-check 修复当前问题，沿用项目约定并完成必要验证。
```

```text
$fork-upstream-sync 检查当前 fork 的上游变化和自有定制，只报告，不修改或发布。
```

`fork-upstream-sync` 的同步、push、PR 和版本发布按当前任务已授权的范围执行。安装 Skill 不会自动创建定时任务或启动同步。

## 维护约定

* 通用工作流放在 Skill 中，项目专有规则留在目标仓库。
* 不将实际运行中的凭据、私有仓库信息、业务记录或本机路径写回通用 Skill。
* 新增或调整 Skill 时，同步更新中英文 README 的索引，并检查本地链接和入口格式。

## 来源

`code-change-check` 的参考来源在其 [来源与维护](code-change-check/SKILL.md#来源与维护) 中列出。

## 许可证

本项目采用 [MIT License](LICENSE)。
