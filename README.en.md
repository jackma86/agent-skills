# Agent Skills

[简体中文](README.md) | English

A collection of reusable workflows for coding agents, covering code changes, self-review, fork synchronization, and version releases.

Each skill provides instructions in its own `SKILL.md` and is independent of any specific project, account, or technology stack. Project rules come from the target repository's `AGENTS.md` and contribution guidelines.

The skill instructions are currently written in Simplified Chinese.

## Skill index

| Skill | Purpose | Use cases |
| --- | --- | --- |
| [code-change-check](code-change-check/SKILL.md) | Trace call paths, make minimal but complete changes, review the full diff, and validate the result | Bug fixes, feature changes, and refactoring |
| [fork-upstream-sync](fork-upstream-sync/SKILL.md) | Identify upstream and fork repositories, preserve customizations, sync upstream changes, and publish traceable fork tags | Fork status checks, upstream merges, and releases based on official upstream tags or branch snapshots |

## Repository structure

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

## Installation and usage

Place each skill directory you need in a skills location supported by your tool. Keep the directory name and `SKILL.md` intact. Follow your tool's documentation for installation paths and invocation methods.

### Codex

The [official Codex documentation](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) lists these options:

* Personal use: `~/.agents/skills/<skill-name>/SKILL.md`.
* Shared within a project: `.agents/skills/<skill-name>/SKILL.md` in the target project.

Copy only the skill directories you need, such as `code-change-check/`. You do not need to place the entire repository in your skills directory. If a skill with the same name already exists at the destination, compare the contents before updating it.

After installation, invoke the skill explicitly in a chat for the target project:

```text
$code-change-check Fix the current issue, follow the project's conventions, and complete the necessary validation.
```

```text
$fork-upstream-sync Check upstream changes and customizations in the current fork. Report only; do not modify or publish anything.
```

For `fork-upstream-sync`, synchronization, pushes, pull requests, and version releases follow the scope authorized by the current task. Installing the skill does not create scheduled tasks or start synchronization automatically.

## Maintenance

* Keep reusable workflows in skills and project-specific rules in the target repository.
* Do not write credentials, private repository information, business records, or local machine paths from actual runs back into shared skills.
* When adding or updating a skill, update the indexes in both READMEs and check local links and skill entry formats.

## Sources

References for `code-change-check` are listed in its [Sources and maintenance](code-change-check/SKILL.md#来源与维护) section.

## License

This project is licensed under the [MIT License](LICENSE).
