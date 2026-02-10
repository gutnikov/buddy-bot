# Create Projects and Worktrees via Bot

## Overview

Add bot commands/flows that let users create new projects (clone a git repo into the work directory) and create new worktrees within existing projects — all through the Telegram bot inline-button interface.

## Current Structure

```
WORK_DIR/
  {project-name}/
    {project-name}/       # main branch checkout (bare clone or initial worktree)
    {branch-name}/        # additional git worktrees
```

Projects are git repos cloned into `WORK_DIR`. Each project directory contains a main checkout (same name as the project) and zero or more git worktree directories for branches.

## Requirements

### Create New Project

- Add a "New Project" button to the project list shown by `/start`
- When tapped, the bot asks the user for a **git clone URL** (as a plain text message)
- The bot clones the repo into `WORK_DIR/{project-name}/{project-name}/` following the existing convention
  - Project name is derived from the repo URL (last path segment, minus `.git`)
- On success, the bot shows a confirmation and returns the user to the project list (or directly to the worktree selection for the new project)
- On failure (invalid URL, clone error, project name already exists), the bot replies with the error

### Create New Worktree

- Add a "New Worktree" button to the worktree list shown after selecting a project
- When tapped, the bot asks the user for a **branch name** (as a plain text message)
- The bot runs `git worktree add ../{branch-name} -b {branch-name}` from the project's main directory
  - This creates a new worktree directory as a sibling to the main checkout and creates a new local branch
- On success, the bot shows a confirmation and returns the user to the worktree list
- On failure (branch already exists, invalid name), the bot replies with the error

## Decisions

- **Private repos**: Supported. The bot runs on the host where SSH keys are already configured, so `git clone` with SSH URLs works out of the box.
- **Existing remote branches**: Deferred to a future iteration. For now, worktree creation always creates a new local branch.
- **Access control**: Only supergroup admins can create projects and worktrees. The bot checks the user's admin status via `getChatMember` before allowing the action.
