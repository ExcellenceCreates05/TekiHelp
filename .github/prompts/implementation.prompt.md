
---
name: tekihelp-implementation
description: Investigate, plan, implement, test, and review TekiHelp development tasks while preserving the existing architecture. Use when implementing features, fixing bugs, or modifying the TekiHelp codebase.
---


# TekiHelp Development Implementation

## 1. Task definition

**Objective:**  
[Describe the exact feature to implement, bug to fix, or improvement to make.]

**Expected outcome:**  
[Describe what the application should do when the task is completed.]

**Acceptance criteria:**  
[List the specific conditions that must be satisfied.]

**Additional context:**  
[Provide relevant information, constraints, examples, or related issues.]

## 2. Investigation

Before modifying any files:

1. Read the repository's `.github/copilot-instructions.md`.
2. Inspect the existing implementation relevant to the task.
3. Identify the responsible modules, functions, classes, and their callers.
4. Trace dependencies and interactions with other components.
5. Inspect existing tests and identify relevant test coverage.
6. Check the current Git working tree to distinguish existing user changes from changes made during this task.

For workflow-related changes, trace both Telegram and Discord runners where relevant.

Use the actual repository structure. Do not assume that a file, function, integration, or capability exists without verifying it.

If information is missing, investigate further or explicitly identify the uncertainty. Do not invent requirements or present assumptions as facts.

## 3. Implementation requirements

1. Follow the established TekiHelp architecture.
2. Keep conversation decisions in the orchestrator, extraction logic in the extraction module, and provider selection in the AI router.
3. Keep provider-specific behaviour inside the appropriate AI adapters and router.
4. Reuse existing components and validation mechanisms where appropriate.
5. Preserve `PartialEvent` and `ValidatedEvent` responsibilities.
6. Preserve human approval before Watch Folder delivery.
7. Preserve existing working functionality unless the task explicitly requires a change.
8. Handle relevant errors, edge cases, and invalid inputs.
9. Avoid unnecessary dependencies and architectural changes.
10. Do not assume calendar or WhatsApp integrations are operational unless verified.

## 4. Restrictions and change control

- Modify only files necessary for the requested task.
- Do not refactor unrelated code.
- Do not change project structure or rename files without approval.
- Do not introduce new dependencies without approval.
- Do not delete existing functionality without approval.
- Do not modify project documentation unless requested.
- Do not hardcode credentials or expose secrets.
- Do not overwrite or discard existing user changes.
- Do not commit, push, merge, or modify Git history.
- Do not install packages or alter environment configuration without approval.
- Do not claim that an untested integration or feature works.
- Obtain explicit approval before modifying any project file, regardless of the size or complexity of the change.
- Approval applies only to the specific implementation plan presented and accepted by the user. Any material expansion of scope requires renewed approval.

## 5. Implementation workflow

### Phase A: Understand

Explain:
- Your understanding of the objective.
- The existing behaviour.
- The expected behaviour after implementation.
- Any ambiguities or missing requirements.

### Phase B: Investigate

Identify:
- Relevant files and their responsibilities.
- Functions, classes, and callers involved.
- Dependencies and affected components.
- Existing tests and potential regression risks.

### Phase C: Plan

**Mandatory approval gate:**

Stop after presenting the implementation plan and wait for explicit user approval before modifying any project file.

This requirement applies to all changes, regardless of size or complexity, including:
- Bug fixes.
- Small code changes.
- New features.
- Refactoring.
- Test modifications.
- Configuration changes.
- Dependency changes.
- Documentation changes.

A request to investigate, explain, diagnose, or propose a solution does not constitute permission to implement it.

Do not create, edit, delete, rename, or overwrite project files before receiving explicit approval.

If the user rejects the proposed plan, revise the plan and request approval again.

If implementation requires changes outside the approved scope, stop and request approval for the revised scope.

### Phase D: Implement

After approval:

1. Implement only the approved changes.
2. Follow existing naming conventions and coding patterns.
3. Keep changes focused and maintainable.
4. Preserve existing functionality.
5. Do not silently expand the task's scope.

If implementation reveals that the approved approach needs significant changes, stop and request approval for the revised approach.

### Phase E: Verify

1. Run focused tests for the modified functionality.
2. Run the relevant broader test suite.
3. Fix failures introduced by the changes.
4. Inspect test output and distinguish passing, failing, and skipped tests.
5. Identify tests that were not run.
6. Distinguish mocked tests from real external-service integration tests.

Do not modify tests merely to make them pass if doing so weakens the intended behaviour or hides a defect.

### Phase F: Review

Inspect the final Git diff.

Confirm:
- Only necessary files were changed.
- No unrelated user changes were overwritten.
- No credentials or secrets were introduced.
- Existing behaviour was preserved where required.
- The implementation matches the approved plan.

Do not commit or push changes.

## 6. Definition of done

The task is complete when:

- The requested functionality has been implemented.
- The acceptance criteria have been addressed.
- Relevant tests have been executed.
- Test results have been accurately reported.
- Existing functionality has been preserved where required.
- The final Git diff has been reviewed.
- Remaining limitations and unverified behaviour have been identified.

## 7. Required completion report

Provide a concise report using this structure:

**1. Implementation summary**
- What was implemented.
- How the new or modified functionality works.

**2. Files changed**

For each file, provide:
- File path.
- What changed.
- Why it changed.
- Modification date.Whether the file was created or modified, and the date of the change

**3. Testing results**
- Exact commands executed.
- Tests passed.
- Tests failed.
- Tests skipped.
- Tests not executed.
- Exact test commands and their actual outputs or summaries.
- Any environmental limitations preventing tests from running.


**4. Verification**
- What was actually verified.
- Whether testing used mocks or real services.

**5. Outstanding issues**
- Known limitations.
- Unresolved problems.
- Additional work requiring approval.

Never claim successful implementation or verification without supporting evidence.