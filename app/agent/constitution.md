# Tekihelp Operational Constitution

This file is the governance layer referenced in Chapter 3/4. It is NOT a
callable tool -- the agent does not "invoke" the Constitution, it is
constrained by it. The critical rules below are enforced in CODE
(cited by file/function), not only by prompt instruction, so correctness
does not depend solely on the language model behaving.

## Rule 1 -- Atomic Rendering
Never render a graphic unless title, date, time AND venue are all present
and normalized.

**Enforced in code:** `app/models/event.py` -- `ValidatedEvent` cannot be
constructed with a missing field (see `all_fields_present` validator).
`app/rendering/engine.py::render_event_graphic` only accepts a
`ValidatedEvent`, never a `PartialEvent`. There is no code path that can
render incomplete data.

## Rule 2 -- No Hallucination
The agent must never invent an event name, date, time, or venue that was
not stated or clearly implied by the user. If information is missing,
ask -- never guess a plausible default.

**Enforced in code:** `app/agent/prompts.py` -- extraction prompt rule 1.
Partially enforced by the per-field validation in
`app/agent/extraction.py`, which drops (rather than guesses a fix for)
any field the model returns in an unnormalized/invalid form.

## Rule 3 -- Temporal Normalization
Convert natural-language temporal expressions (including Swahili-English
code-switched expressions such as "saa nane") into standard values:
dates to `YYYY-MM-DD`, times to `HH:MM AM/PM`.

**Enforced in code:** `app/models/event.py` -- `date_must_be_normalized`
and `time_must_be_normalized` validators reject any value not already in
the required format; the extraction layer is responsible for producing
that format, and a value that fails is treated as not yet known (FIX #2).

## Rule 4 -- Nullification
Messages that are not event announcements (greetings, prayer requests,
small talk) must not create or update an event.

**Enforced in code:** `app/agent/orchestrator.py` -- checks
`outcome.is_event` before doing anything else with the extraction result.

## Rule 5 -- Human Approval
No approved state, no Watch Folder delivery. The agent cannot bypass the
approval stage under any circumstance.

**Enforced in code:** `app/broadcast/watch_folder.py::deliver_to_watch_folder`
is only ever called from the `approve` callback handler in
`app/channels/*_adapter.py` / `app/main.py` -- never from the orchestrator
or extraction/rendering code directly.

## Rule 6 -- Reject Requires Feedback (added Week 2, Fix #3)
A rejected graphic must not simply loop back and re-render identical data.
The agent must ask what to correct, and apply only that correction.

**Enforced in code:** `app/agent/orchestrator.py` --
`WorkflowStatus.AWAITING_CORRECTION` branch; the next user message is
treated as a targeted field update, not a fresh extraction over the
whole event.

## Rule 7 -- Concurrent-Event Guard (added Week 2, Fix #4)
If a new message appears to describe a second, unrelated event while the
current one is still incomplete, the agent must ask for confirmation
rather than silently merging the two.

**Enforced in code:** `app/agent/orchestrator.py` -- checks
`outcome.possible_new_event` before merging; this is a guard, not full
topic-shift detection, and is documented as a known scope boundary in
Chapter 4.

## Rule 8 -- Maximum Iterations
The agent must terminate safely after `MAX_AGENT_ITERATIONS` turns within
a single session rather than loop indefinitely.

**Enforced in code:** `app/agent/orchestrator.py` --
`session.iteration_count` checked against `config.MAX_AGENT_ITERATIONS`
at the top of every turn.
