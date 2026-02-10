# Example Skills

Complete, ready-to-use skill examples covering common use cases.

## 1. Simple Reference Skill (API Conventions)

Background knowledge that Claude applies automatically.

```yaml
---
name: api-conventions
description: REST API design patterns and conventions for this codebase. Use when writing API endpoints, designing routes, or reviewing API code.
---

When writing API endpoints:

**Naming**:
- Use RESTful conventions: POST (create), GET (read), PUT (update), DELETE (delete)
- Lowercase, hyphens for multi-word: `/user-profiles`, not `/userProfiles`
- Version prefix: `/v1/`

**Responses**:
- Consistent error format: `{"error": "message", "code": "ERROR_CODE"}`
- Include `X-Request-ID` header for tracing
- Paginate with `limit`/`offset` query params

**Status codes**:
- 400: Bad request (validation failed)
- 401: Unauthorized (not authenticated)
- 403: Forbidden (insufficient permissions)
- 404: Not found
- 500: Server error (never expose internals)
```

## 2. Task Skill with Arguments (Fix Issue)

Manual-only task triggered by user with an issue number.

```yaml
---
name: fix-issue
description: Fixes a GitHub issue by reading requirements, implementing changes, writing tests, and creating a commit. Use when asked to fix or resolve a GitHub issue.
disable-model-invocation: true
argument-hint: [issue-number]
---

Fix GitHub issue #$ARGUMENTS:

1. **Read the issue**: `gh issue view $ARGUMENTS`
2. **Understand requirements** and acceptance criteria
3. **Find relevant code** using search
4. **Implement the minimal fix** needed
5. **Write or update tests** covering the fix
6. **Run the test suite** to verify nothing breaks
7. **Create a commit**: `Fix #$ARGUMENTS: <brief description>`

Follow coding standards in CLAUDE.md. Keep the change minimal and focused.
```

## 3. Skill with Dynamic Context (PR Summary)

Injects live data from shell commands before Claude sees the content.

```yaml
---
name: pr-summary
description: Summarizes the current pull request with changes, risk assessment, and review notes. Use when reviewing or summarizing a PR.
context: fork
agent: Explore
allowed-tools: Bash(gh *)
---

## Pull request context

- Title and body: !`gh pr view --json title,body`
- PR diff: !`gh pr diff`
- Changed files: !`gh pr diff --name-only`
- Comments: !`gh pr view --comments`

## Task

Provide a structured PR summary:

1. **Overview**: What this PR does in 1-2 sentences
2. **Changes**: List key changes by file/area
3. **Risk assessment**: What could break? What needs careful testing?
4. **Suggestions**: Any improvements or concerns
```

## 4. Read-Only Research Skill (Subagent)

Runs isolated research in an Explore subagent.

```yaml
---
name: deep-research
description: Thoroughly researches a topic in the codebase using isolated context. Use when asked to investigate, explore, or understand how something works in depth.
context: fork
agent: Explore
---

Research $ARGUMENTS thoroughly:

1. **Find relevant files** using Glob patterns and Grep searches
2. **Read and analyze** key files — understand the full picture
3. **Trace relationships** — how do components connect?
4. **Summarize findings** with specific file:line references
5. **Identify patterns** — what conventions or anti-patterns exist?

Be comprehensive. Check multiple directories and naming conventions.
```

## 5. Code Review Skill with Tool Restrictions

Read-only review that can't modify files.

```yaml
---
name: code-review
description: Reviews code for quality, security, and adherence to conventions. Use when asked to review code, check a PR, or audit code quality.
allowed-tools: Read, Grep, Glob, Bash
---

# Code Review

Review the specified code following this checklist:

## Review checklist

- [ ] **Correctness**: Does the code do what it's supposed to?
- [ ] **Error handling**: Are errors caught and handled appropriately?
- [ ] **Security**: No injection vulnerabilities, no exposed secrets, input validated
- [ ] **Performance**: No N+1 queries, no unnecessary loops, efficient algorithms
- [ ] **Readability**: Clear names, appropriate comments, consistent style
- [ ] **Tests**: Are critical paths tested? Any missing edge cases?
- [ ] **Conventions**: Follows project patterns from CLAUDE.md

## Output format

Organize feedback by priority:

### Critical (must fix)
[Issues that will cause bugs or security vulnerabilities]

### Warnings (should fix)
[Issues that may cause problems or are hard to maintain]

### Suggestions (consider)
[Improvements for readability, performance, or style]

Include specific file:line references and show both the current code and suggested fix.
```

## 6. Deploy Skill (Side Effects, Manual Only)

Manual-only task with dangerous side effects.

```yaml
---
name: deploy
description: Deploys the application to the specified environment. Runs tests, builds, and pushes.
disable-model-invocation: true
argument-hint: [environment: staging|production]
allowed-tools: Bash, Read
---

Deploy to $ARGUMENTS:

1. **Verify environment**: Confirm `$ARGUMENTS` is `staging` or `production`
2. **Run tests**: `npm test` — abort if any fail
3. **Build**: `npm run build` — abort if build fails
4. **Deploy**:
   - staging: `npm run deploy:staging`
   - production: `npm run deploy:production`
5. **Verify**: Check the deployment health endpoint
6. **Report**: Summarize what was deployed and any issues

If deploying to production, double-check with the user before step 4.
```

## 7. Background Knowledge Skill (Not User-Invocable)

Domain knowledge Claude uses automatically when relevant.

```yaml
---
name: legacy-payment-context
description: Technical context about the legacy payment processing system. Explains the PaymentGateway module, its constraints, and common pitfalls. Use when working on payment-related code or debugging payment issues.
user-invocable: false
---

## Legacy Payment System

The payment system uses a custom `PaymentGateway` module with these constraints:

- **Transaction IDs** are 24-char hex strings (not UUIDs)
- **Amounts** are stored in cents (integer), never floats
- **Retry logic**: Max 3 retries with exponential backoff (2s, 4s, 8s)
- **Timeout**: Gateway times out at 30s — always handle `TimeoutError`
- **Idempotency**: Every request MUST include `X-Idempotency-Key` header
- **Test mode**: Set `PAYMENT_ENV=sandbox` — never use production keys in tests

## Common Pitfalls

1. **Float arithmetic**: Always use `Math.round()` when converting from dollars to cents
2. **Missing idempotency key**: Gateway silently creates duplicates without it
3. **Stale tokens**: Auth tokens expire every 15 minutes — check before each request
```

## 8. Skill with Supporting Files

```
commit-review/
├── SKILL.md
├── conventions.md
└── examples.md
```

**SKILL.md:**
```yaml
---
name: commit-review
description: Reviews git commits for message quality, change scope, and adherence to conventions. Use when reviewing commits or preparing to merge.
allowed-tools: Read, Grep, Bash
---

# Commit Review

Review recent commits for quality:

1. Run `git log --oneline -10` to see recent commits
2. For each commit, check:
   - Message follows conventions (see [conventions.md](conventions.md))
   - Change is focused on a single concern
   - No accidental files (build artifacts, secrets, large binaries)
3. Provide feedback organized by commit

For example messages, see [examples.md](examples.md).
```

**conventions.md:**
```markdown
# Commit Message Conventions

## Format
```
type(scope): brief description

Optional body with details.

Optional footer (Breaking changes, issue refs).
```

## Types
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `docs`: Documentation only
- `test`: Adding or correcting tests
- `chore`: Build process, tooling, dependencies

## Rules
- Subject line: max 72 chars, imperative mood, no period
- Body: wrap at 72 chars, explain what and why (not how)
- Reference issues: `Fixes #123` or `Closes #456`
```

**examples.md:**
```markdown
# Commit Message Examples

## Good

```
feat(auth): implement JWT-based authentication

Add login endpoint with token generation and validation middleware.
Tokens expire after 24 hours with refresh support.

Closes #142
```

```
fix(reports): correct date formatting in timezone conversion

Use UTC timestamps consistently across report generation.
Previously, local timezone was used for aggregation but UTC for display.

Fixes #298
```

## Bad

```
fixed stuff
```

```
Updated code and added some things for the new feature
```

```
WIP
```
```

## 9. Multi-Argument Skill

```yaml
---
name: migrate-component
description: Migrates a UI component from one framework to another while preserving behavior and tests.
disable-model-invocation: true
argument-hint: [component-name] [from-framework] [to-framework]
---

Migrate the **$0** component from **$1** to **$2**:

1. **Find the component**: Search for `$0` in the codebase
2. **Read the source**: Understand all props, state, effects, and event handlers
3. **Read existing tests**: Understand what behavior is covered
4. **Rewrite in $2**: Preserve all existing behavior exactly
5. **Update imports**: Fix all files that import the component
6. **Update tests**: Rewrite tests for $2 testing patterns
7. **Verify**: Run the test suite to confirm nothing breaks

Preserve: prop interfaces, event handling, accessibility attributes, CSS class names.
```

## 10. Skill with Hooks (Auto-validation)

```yaml
---
name: safe-sql-editor
description: Edits SQL migration files with automatic validation after each change.
allowed-tools: Read, Edit, Write, Bash
hooks:
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "python scripts/validate-sql.py"
---

# SQL Migration Editor

Edit SQL migrations safely. Every file change is automatically validated.

1. Read the existing migration files
2. Make the requested changes
3. (Validation runs automatically after each edit)
4. If validation fails, fix the issue and re-edit
5. Run `python scripts/test-migration.py` to verify the full migration sequence

Never modify migrations that have already been applied to production.
```
