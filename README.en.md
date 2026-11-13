# Agent Skills

[简体中文](README.md) | English

A collection of reusable workflows for coding agents, covering development readiness reviews, code changes and self-review, pull request reviews, iOS UI reviews, UI regression testing, fork synchronization, and version releases.

Each skill provides instructions in its own `SKILL.md` and is independent of any specific project or account. The index identifies its technology stack and scope. Project rules come from the `AGENTS.md`, `CLAUDE.md`, or equivalent instructions recognized by the current tool, along with contribution guidelines.

The skill instructions are currently written in Simplified Chinese.

## Skill index

| Skill | Purpose | Use cases |
| --- | --- | --- |
| [code-change-check](code-change-check/SKILL.md) | Trace call paths, make minimal but complete changes, review the full diff, and validate the result, with a read-only PR review mode | Bug fixes, feature changes, refactoring, and PR reviews |
| [development-preflight](development-preflight/SKILL.md) | Check requirements, acceptance criteria, design, and the technical plan | Readiness reviews and tasks with open scope or behavior decisions |
| [fork-upstream-sync](fork-upstream-sync/SKILL.md) | Identify upstream and fork repositories, preserve customizations, sync upstream changes, and publish traceable fork tags | Fork status checks, upstream merges, and releases based on official upstream tags or branch snapshots |
| [ios-ui-review](ios-ui-review/SKILL.md) | Review runtime screenshots and interactions and document reproducible findings | iOS UI acceptance checks and focused reviews |
| [ui-regression-check](ui-regression-check/SKILL.md) | Select focused UI regression tests, reuse valid builds, and identify failures | Focused iOS / Xcode UI checks with a configurable runner template and tests |

## Repository structure

```text
agent-skills/
├── .gitignore
├── AGENTS.md
├── LICENSE
├── README.md
├── README.en.md
├── code-change-check/
│   ├── SKILL.md
│   └── references/
│       └── git-checks.md
├── development-preflight/
│   └── SKILL.md
├── fork-upstream-sync/
│   ├── SKILL.md
│   └── references/
│       ├── release.md
│       └── validation.md
├── ios-ui-review/
│   └── SKILL.md
└── ui-regression-check/
    ├── SKILL.md
    ├── agents/
    │   └── openai.yaml
    └── scripts/
        ├── run_ui_regression.py
        └── test_ui_regression.py
```

## Installation and usage

Place each skill directory you need in a skills location supported by your tool. Keep the directory name and `SKILL.md` intact. Follow your tool's documentation for installation paths and invocation methods.

### Codex

The [official Codex documentation](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) lists these options:

* Personal use: `~/.agents/skills/<skill-name>/SKILL.md`.
* Shared within a project: `.agents/skills/<skill-name>/SKILL.md` in the target project.

Some existing Codex environments and installers use `$CODEX_HOME/skills`, commonly `~/.codex/skills` when `CODEX_HOME` is unset. Keep using that location if your current tool discovers skills there. Follow the paths reported by your tool and installer, and avoid installing the same skill in both personal directories.

Copy each complete skill directory you need, such as `fork-upstream-sync/` including its `references/`. You do not need to place the entire repository in your skills directory. If a skill with the same name already exists at the destination, compare the contents before updating it.

After installation, invoke the skill explicitly in a chat for the target project:

```text
$code-change-check Fix the current issue, follow the project's conventions, and complete the necessary validation.
```

```text
$fork-upstream-sync Check upstream changes and customizations in the current fork. Report only; do not modify or publish anything.
```

For `fork-upstream-sync`, synchronization, pushes, pull requests, and version releases follow the scope authorized by the current task. Installing the skill does not create scheduled tasks or start synchronization automatically.

### Claude Code

The [official Claude Code documentation](https://code.claude.com/docs/en/skills) lists `~/.claude/skills/<skill-name>/SKILL.md` for personal skills and `.claude/skills/<skill-name>/SKILL.md` in the target project for project skills. Copy the complete skill directory, confirm discovery, then invoke `/code-change-check` or `/fork-upstream-sync`. Installing into a Codex directory does not also install the skill for Claude Code.

## Maintenance

* Keep reusable workflows in skills and project-specific rules in the target repository.
* Keep real target-project names, personal attribution, credentials, private repository information, business records, and absolute machine paths out of documentation, scripts, tests, metadata, and PR descriptions. Label fictional placeholders clearly. Public third-party references and necessary acknowledgments may remain. See [AGENTS.md](AGENTS.md) for public-content conventions.
* When adding or updating a skill, update the indexes in both READMEs and check local links and skill entry formats.

## Acknowledgments

Public references for `code-change-check` are listed in its [References](code-change-check/SKILL.md#参考来源) section.

## License

This project is licensed under the [MIT License](LICENSE).
