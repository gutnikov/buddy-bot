---
name: create-skill
description: Creates Claude Code skills following the Agent Skills open standard and official best practices. Use when the user wants to create a new skill, write a SKILL.md, design a slash command, or build a reusable Claude Code workflow.
disable-model-invocation: true
argument-hint: [skill-name or description of what the skill should do]
---

# Create a Claude Code Skill

You are an expert skill author. Follow this procedure to create a well-structured Claude Code skill based on the user's request.

## Step 1: Gather requirements

Determine from the user's request (or ask if unclear):

1. **What the skill does** — the core task or knowledge it provides
2. **Who invokes it** — user only (`disable-model-invocation: true`), Claude only (`user-invocable: false`), or both (default)
3. **Where it lives** — project (`.claude/skills/`), personal (`~/.claude/skills/`), or plugin (`<plugin>/skills/`)
4. **Whether it needs supporting files** — scripts, templates, references, examples
5. **Whether it runs in a subagent** — isolated context (`context: fork`) or inline (default)
6. **Tool restrictions** — should Claude have limited tool access (`allowed-tools`)

## Step 2: Create the directory structure

Every skill is a directory containing at minimum a `SKILL.md` file:

```
skill-name/
├── SKILL.md              # Required: instructions + metadata
├── references/           # Optional: detailed docs loaded on demand
├── scripts/              # Optional: executable code
├── assets/               # Optional: templates, schemas, static resources
└── examples/             # Optional: example inputs/outputs
```

## Step 3: Write the SKILL.md

### Frontmatter

Write YAML frontmatter between `---` markers. For the full field reference, see [frontmatter-reference.md](frontmatter-reference.md).

The two most important fields:

- **`name`**: Lowercase letters, numbers, hyphens only. Max 64 chars. Must match directory name. This becomes the `/slash-command`.
- **`description`**: What the skill does AND when to use it. Written in **third person**. Max 1024 chars. Claude uses this to decide when to auto-invoke. Be specific, include trigger keywords.

Good description example:
```
description: Reviews pull requests for code quality, security issues, and adherence to team conventions. Use when reviewing PRs, checking code changes, or when asked to review.
```

Bad description example:
```
description: Helps with code
```

### Body content

Write clear Markdown instructions. Two content types:

**Reference skills** (background knowledge Claude applies to current work):
- Conventions, patterns, style guides, domain knowledge
- Typically runs inline (no `context: fork`)
- Often auto-invoked by Claude

**Task skills** (step-by-step actions):
- Deployments, commits, code generation, analysis workflows
- Often uses `disable-model-invocation: true`
- May use `context: fork` for isolation

### Content guidelines

1. **Be concise** — Claude is smart. Only add context it doesn't already have. Challenge each paragraph: "Does this justify its token cost?"
2. **Keep SKILL.md under 500 lines** — Move detailed reference material to separate files
3. **Use concrete examples** — Show expected input/output pairs
4. **Use numbered steps for workflows** — Break complex tasks into sequential steps with a checklist
5. **Include feedback loops** — For quality-critical tasks: run validator → fix errors → repeat
6. **One level of file references** — Link supporting files directly from SKILL.md, never nest references
7. **No time-sensitive info** — Don't include dates or conditional logic based on time
8. **Consistent terminology** — Pick one term and use it throughout
9. **Forward slashes only** — Never use Windows-style backslashes in paths

For detailed best practices and content patterns, see [best-practices.md](best-practices.md).

## Step 4: Add supporting files (if needed)

Reference files from SKILL.md so Claude knows what they contain and when to load them:

```markdown
## Additional resources
- For complete API details, see [references/api.md](references/api.md)
- For usage examples, see [examples/common-patterns.md](examples/common-patterns.md)
```

For scripts, specify whether Claude should **execute** or **read** them:
- Execute: "Run `scripts/validate.py` to check the output"
- Read: "See `scripts/validate.py` for the validation algorithm"

## Step 5: Validate

Before delivering the skill, verify against this checklist:

- [ ] `name` is lowercase, hyphens/numbers only, matches directory name
- [ ] `description` is third-person, specific, includes trigger keywords, states what AND when
- [ ] SKILL.md body is under 500 lines
- [ ] Instructions are clear and actionable
- [ ] Examples are concrete
- [ ] File references are one level deep from SKILL.md
- [ ] No hardcoded secrets, API keys, or passwords
- [ ] No time-sensitive information
- [ ] If scripts are included: they handle errors explicitly, no magic constants

## String substitutions available in skills

| Variable | Description |
|---|---|
| `$ARGUMENTS` | All arguments passed when invoking the skill |
| `$ARGUMENTS[N]` or `$N` | Specific argument by 0-based index |
| `${CLAUDE_SESSION_ID}` | Current session ID |
| `` !`command` `` | Dynamic context injection — runs shell command, output replaces placeholder |

## Quick example: complete skill

```yaml
---
name: fix-issue
description: Fixes a GitHub issue by reading requirements, implementing changes, writing tests, and creating a commit. Use when asked to fix or resolve a GitHub issue by number.
disable-model-invocation: true
argument-hint: [issue-number]
---

Fix GitHub issue #$ARGUMENTS:

1. Read the issue: `gh issue view $ARGUMENTS`
2. Understand requirements and acceptance criteria
3. Find relevant code using search
4. Implement the minimal fix needed
5. Write or update tests
6. Verify tests pass
7. Create a commit: "Fix #$ARGUMENTS: <description>"
```

## Reference files

- [frontmatter-reference.md](frontmatter-reference.md) — Complete field reference for both Claude Code and Agent Skills open standard
- [best-practices.md](best-practices.md) — Detailed authoring best practices, content patterns, anti-patterns
- [advanced-patterns.md](advanced-patterns.md) — Subagent execution, dynamic context, hooks, visual output, plugins
- [examples.md](examples.md) — Full example skills for common use cases
