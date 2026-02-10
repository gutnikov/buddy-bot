---
name: spec
description: "Spec toolkit: create a structured spec from raw text, critique a spec for weaknesses, or review a spec against the codebase. Usage: /spec create|critic|review [input]"
argument-hint: create|critic|review [spec text or raw input]
user-invocable: true
---

# Spec Toolkit

Parse the first word of the arguments to determine the mode, then apply it to the remaining input.

**$ARGUMENTS**

- If the first word is `create` — run **Create Mode**
- If the first word is `critic` — run **Critic Mode**
- If the first word is `review` — run **Review Mode**
- If the first word is none of the above — tell the user: "Usage: `/spec create|critic|review [input]`" and stop

The input is everything after the mode word.

---

## Create Mode — Structure, Don't Invent

Transform the input into a well-structured spec.

### Rules

1. **Never add ideas** — Every point in the output must trace back to something in the input. If the input says "needs auth", write about auth. Do not add "and rate limiting" because it seems related.

2. **Never remove ideas** — Everything in the input must appear in the output. If something seems minor, it still gets a line.

3. **Never assume intent** — If the input is ambiguous, keep it ambiguous. Use the original wording or flag it with "TBD" / "To be clarified". Do not resolve ambiguity by guessing.

4. **Improve clarity, not scope** — You may:
   - Reword for clarity (fix grammar, tighten phrasing)
   - Group related points under headings
   - Reorder for logical flow
   - Add formatting (lists, tables, sections)
   - Split compound sentences into separate requirements

   You may NOT:
   - Add requirements, constraints, or suggestions
   - Add "nice to have" sections with new ideas
   - Expand scope ("this implies we also need...")
   - Add technical implementation details the input didn't mention

### Output Structure

Use whichever sections are relevant — skip sections that have no content from the input:

```markdown
# [Title — derived from the input]

## Overview
[1-3 sentence summary of what this spec covers, using only input content]

## Goals
- [What the input says should be achieved]

## Requirements
- [Concrete requirements extracted from the input]
- [Each as a clear, single-point bullet]

## Constraints
- [Any limitations or boundaries mentioned in the input]

## Open Questions
- [Anything ambiguous or underspecified in the input — flag, don't resolve]
```

Adapt the sections to fit the content. A short input gets a short spec. A detailed input gets detailed sections. Match the depth of the output to the depth of the input.

### Formatting

- Use markdown with clear headings
- One requirement per bullet point
- Keep bullets concise — one sentence each where possible
- Use tables if the input contains structured comparisons or options
- Use `TBD` for anything that needs clarification

---

## Critic Mode — Find What's Wrong

Critically analyze the input spec and produce a clear, honest assessment of its weaknesses.

### Mindset

You are a skeptical reviewer whose job is to prevent wasted implementation effort. Read the spec as someone who has to build exactly what it says — every gap, contradiction, or vague phrase becomes a real problem during development. Be direct and specific. No softening, no "consider perhaps" — state what's wrong and why.

### What to Examine

#### 1. Missing Parts
- What does the spec not cover that it should?
- Are there flows or states with no defined behavior?
- Are error cases, edge cases, or failure modes absent?
- Is the scope defined? Is it clear what's explicitly out of scope?

#### 2. Gaps
- Are there logical steps missing between requirements?
- Does the spec jump from A to C without explaining B?
- Are there actors or systems mentioned without explaining their role?
- Are there inputs with no defined source, or outputs with no defined destination?

#### 3. Inconsistencies
- Do any two statements contradict each other?
- Are terms used inconsistently (same concept, different names — or same name, different meanings)?
- Do stated constraints conflict with stated requirements?
- Are numbers or limits stated in one place and contradicted in another?

#### 4. Illogical Parts
- Are there requirements that don't follow from the stated goals?
- Are there solutions stated without a problem to solve?
- Does the ordering of operations make sense?
- Are there circular dependencies or impossible sequences?

#### 5. Vague Formulations
- Flag every instance of: "appropriate", "as needed", "properly", "efficiently", "flexible", "robust", "seamless", "intuitive", "fast", "secure", "scalable", "handle errors gracefully"
- These words mean nothing without a concrete definition
- For each, state what concrete definition is needed

### Output Format

```markdown
## Spec Critique: [spec title]

### Verdict
[One paragraph: overall assessment — is this spec ready for implementation? What's the biggest problem?]

### Missing
- **[What's missing]** — [Why it matters]

### Gaps
- **[Where the gap is]** — [What's missing between the lines]

### Inconsistencies
- **[Statement A]** vs **[Statement B]** — [Why these conflict]

### Illogical
- **[The requirement]** — [Why it doesn't make sense]

### Vague
- **"[quoted vague phrase]"** — [What concrete definition is needed instead]

### Severity Rating
🔴 Blocking: [count] issues that prevent implementation
🟡 Significant: [count] issues that will cause confusion or rework
⚪ Minor: [count] issues that are worth fixing but won't block progress
```

### Constraints

- **Criticize, don't fix** — Point out problems. Don't rewrite the spec or propose solutions. The author decides how to fix it.
- **Quote the spec** — When flagging an issue, reference or quote the specific part of the spec you're criticizing.
- **No false positives** — Don't manufacture issues to seem thorough. If the spec is solid in an area, skip that section.
- **No praise** — This is a critique, not a review. Don't say what's good. The author knows what they wrote well — they need to know what they didn't.
- **Be proportional** — A one-page spec doesn't need twenty critiques. Scale the depth of criticism to the size and ambition of the spec.

---

## Review Mode — Find the Gaps

Review the input spec, cross-reference it with the codebase, and produce questions that will make it implementation-ready.

### Process

1. **Read the spec carefully** — Understand the full intent, not just the words.

2. **Explore the codebase** — Find the modules, models, workflows, and patterns that this spec would touch. Understand what already exists, what would change, and what's new.

3. **Think critically** — For every requirement, ask yourself:
   - What happens at the edges? (empty input, failures, timeouts, duplicates)
   - What's implied but not stated?
   - What would a developer need to know that isn't here?
   - What decisions are deferred that shouldn't be?
   - Does this conflict with or duplicate anything that already exists?
   - Is there a simpler way to achieve the same goal?

4. **Formulate 5-10 questions** — Each question should, when answered, make the spec more concrete and implementable.

### Question Quality Standards

Every question must be:

- **Specific** — Not "have you thought about error handling?" but "What should happen when the Slack message fails to send after 3 retries — skip silently, queue for retry, or alert an admin?"
- **Actionable** — The answer directly updates the spec. No philosophical questions.
- **Non-obvious** — Don't ask things the spec already answers or that have only one reasonable answer.
- **Grounded in the codebase** — Reference existing patterns, models, or constraints when relevant. Example: "The current `ProjectConfig` model has no `timeout` field — should this spec add one, or reuse `Settings.default_timeout`?"

### When the answer is a choice: provide options

If a question has a finite set of reasonable answers, list them:

```
3. How should duplicate submissions be handled?
   a) Reject with an error — simplest, caller retries if needed
   b) Idempotent — detect duplicate and return the existing result
   c) Allow duplicates — treat each as a new submission
```

Keep option descriptions to one line each. Note the trade-off, not a recommendation.

### What to look for

- **Undefined behavior** — What happens when things go wrong? Timeouts, partial failures, invalid input, race conditions.
- **Missing boundaries** — No limits specified (max size, max count, max duration). No mention of what's out of scope.
- **Vague language** — "should handle errors appropriately", "fast", "secure", "flexible". These need concrete definitions.
- **Implicit dependencies** — The spec assumes something exists or works a certain way without stating it.
- **Conflicting requirements** — Two statements that can't both be true, or a requirement that conflicts with existing code.
- **Missing actors** — Who triggers this? Who gets notified? Who has permission?
- **State gaps** — What state transitions exist? What if the process is interrupted mid-way?
- **Integration blind spots** — How does this interact with existing workflows, models, APIs?

### Output Format

```markdown
## Spec Review: [spec title]

### Context
[2-3 sentences: what this spec is about and which parts of the codebase it touches]

### Questions

1. **[Short label]** — [Full question]
   - Context: [Why this matters / what codebase detail prompted it]

2. **[Short label]** — [Full question with options if applicable]
   a) Option A — [one-line trade-off]
   b) Option B — [one-line trade-off]
   c) Option C — [one-line trade-off]

...

### Summary
[One sentence: the single biggest gap in the spec right now]
```

### Constraints

- **Do not rewrite the spec** — Your job is questions, not answers.
- **Do not recommend** — Present options neutrally. The spec author decides.
- **Do not pad** — If there are only 5 real questions, don't invent 5 more. Aim for 5-10, but quality over quantity.
- **Use common sense** — If the spec says "send a notification" and doesn't say to whom, that's a question. If it says "save to database" and the project uses PostgreSQL, that's not a question.
