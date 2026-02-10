---
allowed-tools: Bash, Read, Glob, Grep, Write, Edit, WebFetch, WebSearch, AskUserQuestion
description: "Guided workflow to create a structured, negotiated spec from raw input. Walks you through drafting, critique, and refinement until the spec is solid."
user-invocable: true
---

# Create Spec — Guided Workflow

You are guiding the user through a structured process to turn raw ideas into a solid, implementation-ready spec. This is an interactive, multi-step workflow — not a one-shot transformation.

## Step 1: Gather Raw Input

If $ARGUMENTS contains text beyond the command name, use that as the raw input.

Otherwise, ask the user:

> What do you want to spec out? Paste your raw notes, ideas, requirements — any format is fine. I'll structure it from there.

Wait for the user's response before proceeding.

## Step 2: Create the Initial Structured Spec

Use the `/spec create` skill on the raw input to produce a structured spec. Present the result to the user.

Then ask:

> Here's the structured version of your input. Take a look — does this capture everything you meant? Anything to add, remove, or clarify before I critique it?

Wait for the user's response. If they have changes, incorporate them and show the updated spec. Repeat until they're satisfied with the draft.

## Step 3: Critique the Spec

Use the `/spec critic` skill on the current spec. Present the critique to the user.

Then ask:

> Here's the critique. Let's go through the issues — which ones do you want to address? For each one, tell me how you'd like to resolve it (or if you want to leave it as-is).

Wait for the user's response. For each issue they want to address:
- Update the spec accordingly
- Show the updated section

After addressing all the issues the user wants to fix, show the full updated spec.

## Step 4: Review Against Codebase

Use the `/spec review` skill on the current spec. Present the review questions to the user.

Then ask:

> These are the implementation questions I found by cross-referencing with the codebase. Let's resolve them — answer whichever ones you can, and we'll update the spec with your decisions.

Wait for the user's response. For each answered question:
- Incorporate the answer into the spec as a concrete requirement or constraint
- Remove it from Open Questions (or move it to a Decisions section)

## Step 5: Final Spec

Present the final spec and ask:

> Here's the final spec with all your decisions incorporated. Want to:
> 1. Save it to a file
> 2. Run another round of critique
> 3. Done — looks good

If they choose to save, ask where they want it saved (suggest a reasonable default like `specs/[name].md` or `docs/specs/[name].md` based on project structure).

## Rules

- **Never skip steps** — Always go through gather → structure → critique → review → finalize
- **Always wait for user input** between steps — This is a conversation, not a monologue
- **Be concise** — Don't repeat the full spec every time unless the user asks or you've made significant changes. Show diffs or updated sections instead.
- **Track changes** — When updating the spec, be clear about what changed and why
- **The user decides** — You present findings and options. The user makes all decisions about scope, trade-offs, and what to include.
