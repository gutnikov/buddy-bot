# Frontmatter Reference

Complete reference for all YAML frontmatter fields in `SKILL.md`.

## Claude Code Frontmatter Fields

All fields are optional. Only `description` is recommended.

| Field | Required | Default | Description |
|---|---|---|---|
| `name` | No | Directory name | Display name and `/slash-command`. Lowercase letters, numbers, and hyphens only. Max 64 chars. Must not start/end with hyphen. No consecutive hyphens. |
| `description` | Recommended | First paragraph of body | What the skill does and when to use it. Claude uses this to decide when to auto-invoke. Max 1024 chars. Write in third person. |
| `argument-hint` | No | None | Hint shown during autocomplete. Example: `[issue-number]` or `[filename] [format]`. |
| `disable-model-invocation` | No | `false` | Set to `true` to prevent Claude from automatically loading this skill. Only manual `/name` invocation works. Use for workflows with side effects (deploy, commit, send messages). |
| `user-invocable` | No | `true` | Set to `false` to hide from the `/` menu. Only Claude can invoke automatically. Use for background knowledge (legacy system context, domain conventions). |
| `allowed-tools` | No | Inherit all | Tools Claude can use without asking permission when this skill is active. Comma-separated: `Read, Grep, Glob`. Use `Bash(pattern *)` for restricted bash. |
| `model` | No | Inherit | Model to use: `sonnet`, `opus`, `haiku`, or `inherit`. |
| `context` | No | None (inline) | Set to `fork` to run in an isolated subagent context with its own context window. |
| `agent` | No | `general-purpose` | When `context: fork` is set, which subagent type to use: `Explore` (read-only, fast), `Plan` (research), `general-purpose` (all tools), or any custom subagent name from `.claude/agents/`. |
| `hooks` | No | None | Lifecycle hooks scoped to this skill. Events: `PreToolUse`, `PostToolUse`, `Stop`. |

## Invocation Control Matrix

| Frontmatter | User can invoke | Claude can invoke | Description loaded into context |
|---|---|---|---|
| (default) | Yes | Yes | Yes — full skill loads when invoked |
| `disable-model-invocation: true` | Yes | No | No — only loads when user invokes with `/` |
| `user-invocable: false` | No | Yes | Yes — full skill loads when Claude decides it's relevant |

## Agent Skills Open Standard Fields (agentskills.io)

Per the open standard specification at https://agentskills.io/specification:

| Field | Required | Constraints |
|---|---|---|
| `name` | Yes | Max 64 chars. Lowercase letters, numbers, hyphens only. Must not start/end with hyphen. No consecutive hyphens (`--`). Must match the parent directory name. |
| `description` | Yes | Max 1024 chars. Non-empty. Describes what the skill does and when to use it. No XML tags. |
| `license` | No | License name or reference to a bundled license file. |
| `compatibility` | No | Max 500 chars. Indicates environment requirements (intended product, system packages, network access). |
| `metadata` | No | Arbitrary key-value string mapping for additional metadata (author, version, etc.). |
| `allowed-tools` | No | Space-delimited list of pre-approved tools (experimental). |

## Name Validation Rules

Valid:
- `pdf-processing`
- `code-review`
- `deploy`
- `my-skill-v2`

Invalid:
- `PDF-Processing` (uppercase)
- `-pdf` (starts with hyphen)
- `pdf-` (ends with hyphen)
- `pdf--processing` (consecutive hyphens)
- `my skill` (spaces)
- `my_skill` (underscores)

## String Substitution Variables

Available in the markdown body of SKILL.md:

| Variable | Description | Example |
|---|---|---|
| `$ARGUMENTS` | All arguments passed when invoking the skill | `/fix-issue 123` → `$ARGUMENTS` = `123` |
| `$ARGUMENTS[N]` | Specific argument by 0-based index | `/migrate Button React Vue` → `$ARGUMENTS[1]` = `React` |
| `$N` | Shorthand for `$ARGUMENTS[N]` | `$0` = first arg, `$1` = second |
| `${CLAUDE_SESSION_ID}` | Current session ID | Useful for logging, session-specific files |
| `` !`command` `` | Dynamic context injection | Runs shell command before Claude sees content, output replaces placeholder |

If `$ARGUMENTS` is not present in the skill content but arguments are passed, Claude Code appends `ARGUMENTS: <value>` to the end.

## Complete Frontmatter Example

```yaml
---
name: deploy-staging
description: Deploys the application to the staging environment. Runs tests, builds the app, and pushes to staging. Use when asked to deploy to staging or test a release.
disable-model-invocation: true
argument-hint: [branch-name]
allowed-tools: Bash, Read, Grep
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-deploy-command.sh"
  Stop:
    - hooks:
        - type: command
          command: "./scripts/notify-deploy-complete.sh"
---
```
