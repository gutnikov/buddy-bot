# Crunch: Full Issue Implementation Workflow

Implement a GitHub issue end-to-end: code, tests, PR, review, merge.

## Arguments

- `$ARGUMENTS` — GitHub issue number (e.g., "8" or "#8")

## Workflow

Execute the following steps sequentially. Log progress to `issue-{ID}.log` after each major step.

### Phase 1: Setup

1. **Parse issue ID** from arguments (strip # if present)
2. **Initialize log file**: `issue-{ID}.log`
3. **Fetch issue details**: `gh issue view {ID}`
4. **Log**: "Starting work on issue #{ID}: {title}"

### Phase 2: Implementation

1. **Read the issue** thoroughly — understand requirements, DOD, test requirements
2. **Check dependencies** — if issue depends on others, verify they're closed
3. **Create feature branch**: `git checkout -b issue-{ID}-{slug}`
4. **Implement the code** following the issue requirements
5. **Implement tests** as specified in the issue
6. **Log**: "Implementation complete"

### Phase 3: Validation

1. **Run tests in Docker**: `make test`
2. **If tests fail**:
   - Analyze failures
   - Fix issues
   - Re-run tests
   - Repeat until passing
3. **Log**: "Tests passing"

### Phase 4: Pull Request

1. **Commit changes** with descriptive message referencing issue
2. **Push branch**: `git push -u origin issue-{ID}-{slug}`
3. **Create PR**:
   ```
   gh pr create --title "Issue #{ID}: {title}" --body "Closes #{ID}\n\n## Summary\n{description}\n\n## Test Plan\n- [x] All tests passing via \`make test\`"
   ```
4. **Log**: "PR created: {pr_url}"

### Phase 5: Code Review

1. **Run code review** using `/code-review` skill on the PR
2. **Analyze findings**:
   - Critical/blocking issues: must fix
   - Suggestions: fix if reasonable
   - Nitpicks: fix if trivial
3. **Fix findings** and push updates
4. **Log**: "Code review complete, {N} issues addressed"

### Phase 6: Documentation

1. **Check if README needs updates**:
   - New public API? Document it
   - New dependencies? Document installation
   - New make commands? Document usage
2. **Check if CLAUDE.md needs updates**:
   - New patterns or conventions established?
   - Important architectural decisions?
3. **Commit documentation updates** if any
4. **Log**: "Documentation updated" (or "No documentation changes needed")

### Phase 7: Merge

1. **Verify PR checks passing** (if CI configured)
2. **Merge PR**: `gh pr merge --squash --delete-branch`
3. **Log**: "PR merged successfully"
4. **Close issue** if not auto-closed: `gh issue close {ID}`
5. **Log**: "Issue #{ID} complete"

## Logging Format

Write to `issue-{ID}.log`:

```
[2024-01-15 10:30:00] Starting work on issue #8: Docker setup
[2024-01-15 10:35:00] Implementation complete
[2024-01-15 10:40:00] Tests passing
[2024-01-15 10:42:00] PR created: https://github.com/owner/repo/pull/123
[2024-01-15 10:50:00] Code review complete, 3 issues addressed
[2024-01-15 10:52:00] Documentation updated
[2024-01-15 10:55:00] PR merged successfully
[2024-01-15 10:55:00] Issue #8 complete
```

## Error Handling

If any step fails:
1. **Log the error**: `[timestamp] ERROR: {description}`
2. **Attempt to recover** if possible
3. **If unrecoverable**: Log final state and stop

## Important Notes

- **Always run tests in Docker**: `make test`, never `pytest` directly
- **Keep commits atomic**: One logical change per commit
- **Follow existing patterns**: Read surrounding code before writing new code
- **Check the spec**: Reference `specs/terminal-replay-renderer.md` for requirements
- **DOD is mandatory**: Every checkbox in Definition of Done must be satisfied

## Example Usage

```bash
# Via Claude CLI
claude -p "/crunch 8"

# Via shell script
bin/crunch.sh 8
```
