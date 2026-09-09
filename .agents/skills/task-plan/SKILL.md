---
name: task-plan
description: Create a repository-aware implementation plan for a single engineering task and persist it as a Markdown file under .agents/plan. Use when asked to investigate, scope, or plan a specific change before implementation.
---

# Individual Task Plan

Produce an implementation-ready plan for one task. Planning is the deliverable: do not implement the requested product change unless the user separately asks for implementation.

## Investigate the Task

1. Find the repository root and read its `AGENTS.md` plus any more specific `AGENTS.md` files governing the likely implementation paths.
2. Inspect the relevant source, tests, configuration, schemas, and documentation. Trace existing patterns and dependencies far enough that the plan refers to actual files, symbols, and commands instead of hypothetical structure.
3. Reconcile the request with repository constraints. Make reasonable, low-risk assumptions when the code provides enough evidence; surface consequential ambiguity rather than inventing behavior.
4. Check the working tree and preserve existing changes. Do not modify implementation files while producing the plan.

## Persist the Plan

Write the result to `<repo-root>/.agents/plan/<meaningful-task-name>.md`.

- Use a concise, descriptive kebab-case filename derived from the task, such as `add-order-domain-models.md`.
- Create `.agents/plan` when it does not exist.
- If a plan for the same task already exists, update that file rather than creating a duplicate. Do not overwrite a differently scoped plan.
- Keep the plan self-contained so another engineer can implement it without rereading the original conversation.

Use this structure:

```markdown
# <Task title>

## Goal and overview

<Desired outcome, current-state context, and the general execution approach.>

## Scope

### In scope

- <Components, files/areas, interfaces, and behaviors the plan may change.>

### Out of scope

- <Adjacent code, behavior, refactors, or systems that must remain unchanged.>

## Acceptance criteria

- [ ] <Specific, observable condition that demonstrates completion.>

## Implementation tasks

- [ ] 1. <Task title>
  - Files/areas: `<known paths or symbols>`
  - Instructions: <Concrete change to make, important behavior, constraints, and dependencies.>
  - Validation: <Focused check proving this task is complete.>

## Blockers and open questions

- <Unresolved question, why it matters, and what decision or information is needed.>
```

## Plan Quality

- Define concrete scope boundaries. Identify the expected or permitted touchpoints and explicitly protect adjacent parts of the codebase that the task does not require changing. Keep every implementation task within those boundaries; if completion requires expanding them, record that as an open question instead of silently broadening the plan.
- Define acceptance criteria in observable terms; cover success behavior, relevant failure or edge cases, and repository-mandated constraints.
- Order implementation tasks by dependency. Keep each task specific enough to execute, and name known files or symbols without inventing paths that do not exist.
- Include validation with the task it verifies. Put commands in the plan only when they are confirmed by repository documentation or configuration.
- For any plan that changes code, include at least one explicit task to add or update automated tests. Describe the behavior and edge cases the tests must cover; do not rely only on a generic final command such as “run the test suite.”
- Include documentation, migration, configuration, observability, or rollout work only when the task or repository evidence calls for it.
- In `Blockers and open questions`, write `None.` when no unresolved blockers or consequential questions remain. Record assumptions there when a different answer would materially change the plan.

Before finishing, verify that the plan file exists at the required location, contains all five sections, that every implementation task stays within the stated scope, and that every acceptance criterion is addressed by one or more implementation tasks.
