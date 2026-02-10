# Advanced Patterns

Advanced skill features: subagent execution, dynamic context, hooks, visual output, plugins, and permissions.

## Running Skills in a Subagent

Add `context: fork` to run a skill in isolation with its own context window. The skill content becomes the prompt that drives the subagent. It won't have access to conversation history.

```yaml
---
name: deep-research
description: Research a topic thoroughly
context: fork
agent: Explore
---

Research $ARGUMENTS thoroughly:
1. Find relevant files using Glob and Grep
2. Read and analyze the code
3. Summarize findings with specific file references
```

### How It Works

1. A new isolated context is created
2. The subagent receives the skill content as its prompt
3. The `agent` field determines the execution environment (model, tools, permissions)
4. Results are summarized and returned to the main conversation

### Agent Types

| Agent | Model | Tools | Best For |
|---|---|---|---|
| `Explore` | Haiku (fast) | Read-only | File discovery, code search, codebase exploration |
| `Plan` | Inherits | Read-only | Codebase research for planning |
| `general-purpose` | Inherits | All tools | Complex tasks requiring exploration and modification |
| Custom name | As configured | As configured | Any custom subagent from `.claude/agents/` |

### Important

- `context: fork` only makes sense for skills with explicit task instructions
- If the skill contains only guidelines without a task, the subagent has no actionable prompt
- Subagents cannot spawn other subagents

### Skills vs Subagents

| Approach | System prompt | Task | Also loads |
|---|---|---|---|
| Skill with `context: fork` | From agent type | SKILL.md content | CLAUDE.md |
| Subagent with `skills` field | Subagent's body | Claude's delegation message | Preloaded skills + CLAUDE.md |

### Preloading Skills into Subagents (inverse pattern)

In a subagent definition (`.claude/agents/`), preload skills:

```yaml
---
name: api-developer
description: Implement API endpoints following team conventions
skills:
  - api-conventions
  - error-handling-patterns
---

Implement API endpoints. Follow conventions from preloaded skills.
```

The full content of each skill is injected at startup. Subagents don't inherit skills from the parent conversation.

## Dynamic Context Injection

The `` !`command` `` syntax runs shell commands before the skill content is sent to Claude. The command output replaces the placeholder.

```yaml
---
name: pr-summary
description: Summarize changes in a pull request
context: fork
agent: Explore
allowed-tools: Bash(gh *)
---

## Pull request context
- PR diff: !`gh pr diff`
- PR comments: !`gh pr view --comments`
- Changed files: !`gh pr diff --name-only`
- PR metadata: !`gh pr view --json title,body,author`

## Your task
Summarize this pull request with:
1. What changed and why
2. Risk assessment
3. Questions or concerns
```

### How It Works

1. Each `` !`command` `` executes immediately (before Claude sees anything)
2. The command output replaces the placeholder in the skill content
3. Claude receives the fully-rendered prompt with actual data
4. This is **preprocessing**, not something Claude executes later

## Restricting Tool Access

Use `allowed-tools` to limit what Claude can do when a skill is active:

```yaml
---
name: safe-reader
description: Read files without making changes
allowed-tools: Read, Grep, Glob
---
```

### Bash Restrictions with Patterns

```yaml
# Only allow git and gh commands
allowed-tools: Bash(git *), Bash(gh *)

# Only allow python execution
allowed-tools: Bash(python *)

# Read-only tools plus restricted bash
allowed-tools: Read, Grep, Glob, Bash(git status), Bash(git log *)
```

## Hooks in Skills

Skills can define lifecycle hooks that run during skill execution:

```yaml
---
name: safe-editor
description: Edit files with automatic validation
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-command.sh"
  PostToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: "./scripts/run-linter.sh"
  Stop:
    - hooks:
        - type: command
          command: "./scripts/cleanup.sh"
---
```

### Available Hook Events

| Event | Matcher Input | When |
|---|---|---|
| `PreToolUse` | Tool name | Before the skill uses a tool |
| `PostToolUse` | Tool name | After the skill uses a tool |
| `Stop` | (none) | When the skill finishes |

Hook commands receive JSON input via stdin with tool details. Exit code 2 blocks the operation.

## Generating Visual Output

Skills can bundle scripts that produce interactive HTML:

```yaml
---
name: codebase-visualizer
description: Generate an interactive tree visualization of your codebase
allowed-tools: Bash(python *)
---

# Codebase Visualizer

Run the visualization script from your project root:

```bash
python ~/.claude/skills/codebase-visualizer/scripts/visualize.py .
```

This creates `codebase-map.html` and opens it in your browser.
```

This pattern works for: dependency graphs, test coverage reports, API documentation, database schema visualizations, or any data that benefits from interactive exploration.

## Extended Thinking

Include the word **"ultrathink"** anywhere in your skill content to enable Claude's extended thinking (reasoning mode):

```yaml
---
name: architecture-review
description: Deep architecture analysis
---

# Architecture Review (ultrathink)

Analyze the system architecture thoroughly...
```

## Skills with Executable Code

### Scripts Should Solve, Not Punt

Handle errors in scripts rather than failing:

```python
# Good: handles errors explicitly
def process_file(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        print(f"File {path} not found, creating default")
        with open(path, 'w') as f:
            f.write('')
        return ''
```

### Document All Constants

```python
# Good: self-documenting
REQUEST_TIMEOUT = 30  # HTTP requests typically complete within 30 seconds
MAX_RETRIES = 3       # Most intermittent failures resolve by second retry

# Bad: magic numbers
TIMEOUT = 47
RETRIES = 5
```

### Prefer Pre-made Scripts over Generated Code

Benefits: more reliable, save tokens, save time, ensure consistency.

Make clear in instructions whether Claude should **execute** or **read** a script:
- Execute: "Run `scripts/validate.py` to check the output"
- Read: "See `scripts/validate.py` for the validation algorithm"

### Verifiable Intermediate Outputs

For complex tasks, use the plan-validate-execute pattern:

1. Analyze input
2. Create a plan file (e.g., `changes.json`)
3. Validate the plan with a script
4. Execute only after validation passes
5. Verify the output

Validation scripts should provide verbose, specific error messages:
```
"Field 'signature_date' not found. Available fields: customer_name, order_total, signature_date_signed"
```

## Sharing and Distributing Skills

### Scope Options

| Method | Path | Audience |
|---|---|---|
| Project | `.claude/skills/` committed to git | Project contributors |
| Personal | `~/.claude/skills/` | You, across all projects |
| Plugin | `<plugin>/skills/` | Plugin users |
| Enterprise | Managed settings | All organization users |

### Plugin Distribution

Package skills in a plugin:

```
my-plugin/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── code-review/
        └── SKILL.md
```

`plugin.json`:
```json
{
  "name": "my-plugin",
  "description": "Team code review skills",
  "version": "1.0.0",
  "author": { "name": "Team Name" }
}
```

Plugin skills are namespaced: `/my-plugin:code-review`.

Test locally: `claude --plugin-dir ./my-plugin`

Install from marketplace: `/plugin install my-plugin@marketplace-name`

### Converting Standalone to Plugin

1. Create plugin directory with `.claude-plugin/plugin.json`
2. Copy `.claude/skills/` → `my-plugin/skills/`
3. Copy `.claude/commands/` → `my-plugin/commands/`
4. Copy `.claude/agents/` → `my-plugin/agents/`
5. Test with `claude --plugin-dir ./my-plugin`

## Skill Permissions Control

### Deny All Skills

In `/permissions` deny rules: `Skill`

### Allow/Deny Specific Skills

```
# Allow only specific skills
Skill(commit)
Skill(review-pr *)

# Deny specific skills
Skill(deploy *)
```

Pattern syntax: `Skill(name)` for exact match, `Skill(name *)` for prefix match with any arguments.

### Context Budget

Default skill description budget: 15,000 characters. If you have many skills, descriptions may be excluded.

Check: Run `/context` to see warnings about excluded skills.

Increase: Set `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable.
