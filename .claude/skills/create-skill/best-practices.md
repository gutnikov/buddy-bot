# Best Practices for Skill Authoring

Comprehensive guide to writing effective skills. Based on official Anthropic documentation.

## Core Principles

### 1. Be Concise — Context Is a Shared Resource

The context window is shared between the system prompt, conversation history, other skills' metadata, and your request. Only add information Claude doesn't already have.

Challenge each piece of content:
- "Does Claude really need this explanation?"
- "Can I assume Claude knows this?"
- "Does this paragraph justify its token cost?"

**Good** (~50 tokens):
```markdown
## Extract PDF text

Use pdfplumber for text extraction:

```python
import pdfplumber
with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```
```

**Bad** (~150 tokens):
```markdown
## Extract PDF text

PDF (Portable Document Format) files are a common file format that contains text, images, and other content. To extract text from a PDF, you'll need to use a library. There are many libraries available...
```

### 2. Set Appropriate Degrees of Freedom

Match specificity to how fragile the task is:

**High freedom** (text-based instructions) — when multiple approaches are valid:
```markdown
## Code review process
1. Analyze code structure and organization
2. Check for potential bugs or edge cases
3. Suggest improvements for readability
4. Verify adherence to project conventions
```

**Medium freedom** (pseudocode/templates) — when a preferred pattern exists:
```markdown
## Generate report
Use this template and customize as needed:
```python
def generate_report(data, format="markdown", include_charts=True):
    # Process data, generate output, optionally include visualizations
```
```

**Low freedom** (exact scripts) — when operations are fragile:
```markdown
## Database migration
Run exactly this script:
```bash
python scripts/migrate.py --verify --backup
```
Do not modify the command or add additional flags.
```

**Analogy**: Think of Claude navigating a path:
- **Narrow bridge with cliffs**: Only one safe way — provide exact instructions (low freedom)
- **Open field**: Many paths lead to success — give general direction (high freedom)

### 3. Test with All Target Models

Skills behave differently across models:
- **Haiku** (fast, economical): Does the skill provide enough guidance?
- **Sonnet** (balanced): Is the skill clear and efficient?
- **Opus** (powerful reasoning): Does the skill avoid over-explaining?

What works for Opus might need more detail for Haiku.

## Writing Effective Descriptions

The `description` field is the single most important field. Claude uses it to decide which skill to activate from potentially 100+ available skills.

### Rules

1. **Always third person**: "Processes files" not "I process files" or "You can use this to process files"
2. **State what AND when**: Include both what the skill does and when to use it
3. **Include trigger keywords**: Words users naturally say when they need this skill
4. **Be specific**: "Helps with documents" is useless

### Good Examples

```yaml
# PDF processing
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.

# Git commit helper
description: Generate descriptive commit messages by analyzing git diffs. Use when the user asks for help writing commit messages or reviewing staged changes.

# Excel analysis
description: Analyze Excel spreadsheets, create pivot tables, generate charts. Use when analyzing Excel files, spreadsheets, tabular data, or .xlsx files.
```

### Bad Examples

```yaml
description: Helps with documents
description: Processes data
description: Does stuff with files
```

## Naming Conventions

Use **gerund form** (verb + -ing) or action-oriented names. Must be lowercase letters, numbers, and hyphens only.

**Good**: `processing-pdfs`, `analyzing-spreadsheets`, `code-review`, `deploy`, `testing-code`

**Acceptable alternatives**: `pdf-processing`, `spreadsheet-analysis`, `process-pdfs`

**Avoid**: `helper`, `utils`, `tools` (vague), `documents`, `data` (generic)

## Progressive Disclosure

### Three Levels of Loading

| Level | When | Token Cost | Content |
|---|---|---|---|
| Metadata | Always at startup | ~100 tokens/skill | `name` + `description` |
| Instructions | When skill triggered | < 5,000 tokens | SKILL.md body |
| Resources | As needed | Unlimited | Supporting files, scripts |

### Practical Guidelines

- Keep SKILL.md body under **500 lines**
- Split content into separate files when approaching this limit
- Structure SKILL.md as a table of contents pointing to detailed files
- Reference files one level deep — never nest references

### Organization Patterns

**Pattern 1: High-level guide with references**
```markdown
# PDF Processing
## Quick start
[core instructions here]
## Advanced features
- **Form filling**: See [FORMS.md](FORMS.md)
- **API reference**: See [REFERENCE.md](REFERENCE.md)
```

**Pattern 2: Domain-specific organization**
```
bigquery-skill/
├── SKILL.md (overview + navigation)
└── reference/
    ├── finance.md (revenue metrics)
    ├── sales.md (pipeline data)
    └── product.md (usage analytics)
```

**Pattern 3: Conditional details**
```markdown
## Creating documents
Use docx-js for new documents. See [DOCX-JS.md](DOCX-JS.md).
## Editing documents
For simple edits, modify XML directly.
**For tracked changes**: See [REDLINING.md](REDLINING.md)
```

### Long Reference Files

For reference files over 100 lines, include a table of contents at the top:
```markdown
# API Reference
## Contents
- Authentication and setup
- Core methods (create, read, update, delete)
- Advanced features (batch operations, webhooks)
- Error handling patterns
- Code examples
```

## Workflows and Feedback Loops

### Use Checklists for Complex Tasks

```markdown
## Deployment workflow

Copy this checklist and track progress:

```
Task Progress:
- [ ] Step 1: Run test suite
- [ ] Step 2: Build application
- [ ] Step 3: Run validation
- [ ] Step 4: Deploy to target
- [ ] Step 5: Verify deployment
```
```

### Implement Feedback Loops

The validate-fix-repeat pattern greatly improves output quality:

```markdown
1. Make your edits
2. **Validate immediately**: `python scripts/validate.py`
3. If validation fails:
   - Review error messages carefully
   - Fix the issues
   - Run validation again
4. **Only proceed when validation passes**
```

## Content Patterns

### Template Pattern

For strict output format requirements:
```markdown
## Report structure
ALWAYS use this exact template:

# [Analysis Title]
## Executive summary
[One-paragraph overview of key findings]
## Key findings
- Finding 1 with supporting data
- Finding 2 with supporting data
## Recommendations
1. Specific actionable recommendation
```

### Examples Pattern

Show input/output pairs to clarify expected style:
```markdown
## Commit message format

**Example 1:**
Input: Added user authentication with JWT tokens
Output:
```
feat(auth): implement JWT-based authentication
Add login endpoint and token validation middleware
```

**Example 2:**
Input: Fixed bug where dates displayed incorrectly
Output:
```
fix(reports): correct date formatting in timezone conversion
Use UTC timestamps consistently across report generation
```
```

### Conditional Workflow Pattern

```markdown
1. Determine the modification type:
   **Creating new content?** → Follow "Creation workflow" below
   **Editing existing content?** → Follow "Editing workflow" below
```

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Do This Instead |
|---|---|---|
| Windows-style paths (`scripts\helper.py`) | Breaks on Unix systems | Always use forward slashes |
| Too many options ("use pypdf, or pdfplumber, or PyMuPDF...") | Confuses Claude | Provide one default with escape hatch |
| Deeply nested references (A→B→C) | Claude may partially read files | Keep references one level deep |
| Time-sensitive info ("before August 2025...") | Becomes wrong over time | Use "old patterns" section |
| Inconsistent terminology | Confuses Claude | Pick one term, use throughout |
| Vague descriptions | Claude can't discover the skill | Be specific with keywords |
| Over-explaining basics | Wastes tokens | Claude already knows common concepts |
| Magic numbers in scripts | Claude can't reason about them | Document all constants |

## Evaluation-Driven Development

Build evaluations BEFORE writing extensive documentation:

1. **Identify gaps**: Run Claude on representative tasks without a skill. Document failures.
2. **Create evaluations**: Build 3+ scenarios that test these gaps
3. **Establish baseline**: Measure Claude's performance without the skill
4. **Write minimal instructions**: Just enough to address the gaps
5. **Iterate**: Execute evaluations, compare against baseline, refine

### Iterative Development with Claude

1. Complete a task with Claude A using normal prompting — note what context you repeatedly provide
2. Identify the reusable pattern
3. Ask Claude A to create a Skill capturing that pattern
4. Review for conciseness — remove anything Claude already knows
5. Test with Claude B (fresh instance with skill loaded) on similar tasks
6. Observe Claude B's behavior — note where it struggles
7. Return to Claude A with specifics: "Claude B forgot to filter test accounts"
8. Apply refinements and retest

## Security Considerations

- Never hardcode API keys, passwords, or credentials
- Review all files in downloaded skills before enabling
- Use MCP connections for external service access
- Skills that fetch from external URLs can be compromised over time
- Treat installing a skill like installing software — only from trusted sources
- Scripts in skills can execute arbitrary code — audit them
