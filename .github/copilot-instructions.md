# TekiHelp Project Instructions

## Architecture

- Telegram starts from `app.main`; Discord starts from `app.channels.discord_runner`.
- Conversation decisions belong in `app.agent.orchestrator`; extraction belongs in `app.agent.extraction`; provider selection belongs in `app.ai.router`.
- `PartialEvent` represents an event in progress; `ValidatedEvent` is the renderer's input.
- The active runners use `SQLiteSessionStore` from `app.storage.database` for persistence.
- Rendering creates previews. Approved delivery goes through `app.broadcast.watch_folder.deliver_to_watch_folder`, called by the channel approval handlers.
- Do not assume calendar support is wired into the live workflow merely because related modules exist.
- Manual scripts currently live in `testscripts/`, not `scripts/`.
- When repository code, tests, and documentation do not establish how something works, investigate further or explicitly identify the uncertainty. Never present assumptions as verified behaviour.

## Implementation discipline
 - Obtain explicit user approval before modifying any project file, regardless of the change's size or complexity.
- Make only changes necessary for the explicitly requested task.
- Do not refactor unrelated code, rename files, change project structure, or introduce new dependencies without approval.
- Before implementing complex workflow changes, inspect the relevant files, callers, dependencies, and tests.
- For significant changes, first explain the proposed implementation and identify the files that will be affected.
- Preserve existing functionality unless the task explicitly requires changing it.
- Do not invent functionality or assume incomplete integrations are operational.

## Security and configuration
- Never hardcode API keys, passwords, access tokens, or other secrets.
- Use environment variables and the existing configuration system.
- Never expose secrets in logs, test output, source code, or Git commits.
- Preserve environment and dependency configuration unless a change is necessary and approved.

## Git and change control
- Do not commit, push, merge, delete branches, or modify Git history without explicit permission.
- Do not discard or overwrite user changes.
- Before completing a task, inspect the Git diff and list modified files.
- Clearly distinguish changes made for the requested task from pre-existing modifications.

## Testing and reporting
- Run tests relevant to the changes first, followed by the appropriate broader test suite.
- Report the exact test commands executed and their actual results.
- Distinguish passing tests, failing tests, skipped tests, and tests that were not run.
- Do not claim that a feature, integration, or workflow works unless it has actually been tested.
- Where real external services are required, distinguish mocked test results from real integration testing.
- Do not create additional documentation or reports unless requested.
- For every task, report the files changed, the reason for each change, and the date of the modification date.
- For every task, report each file created or modified, why it changed, and the date of the change.
