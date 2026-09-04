# Implementation Plan — Kestrel Warehouse MCP Toolkit

This document explains how the toolkit defined in `spec.md` will be implemented.

The goal of this project is not simply to expose warehouse data through MCP tools. The objective is to provide a toolkit that an agent can use safely and reliably, while enforcing site boundaries, surfacing ambiguity instead of guessing, and requiring explicit approval before any action that changes operational data.

## Architecture Philosophy

The implementation follows the design decisions captured in `spec.md`.

A few principles guide the solution:

- Read-only actions and state-changing actions remain clearly separated.
- Site restrictions are enforced by the toolkit rather than trusted to user input.
- Ambiguous results are surfaced to the user instead of being guessed by the agent.
- Confirmation is required before any operation that could affect warehouse records.
- Error responses should help the agent recover automatically whenever possible.

## Project Structure

Rather than placing all logic inside tool handlers, responsibilities are separated into dedicated modules:

- `data_store.py` loads and manages warehouse data.
- `confirmation.py` manages approval workflows.
- `errors.py` provides consistent, actionable error responses.
- `models.py` defines schema validation through Pydantic.
- `server.py` focuses on MCP registration and tool orchestration.

This separation keeps the system easier to test, understand and maintain.

## Data Management

The toolkit operates on a single warehouse site at a time.

When the server starts, it loads stock and dock information for the configured site only. Data belonging to other sites is never loaded into memory. This provides a stronger form of isolation than accepting a site parameter and validating it later.

The data store is also responsible for:

- Stock lookups
- Dock scheduling
- Open exceptions
- Audit records for confirmed changes

All confirmed state changes are written to an audit trail so that operational decisions remain traceable.

## Confirmation Workflow

State-changing actions follow a preview-and-confirm workflow.

Instead of using a simple `confirmed=true` flag, every pending action receives a unique confirmation ID.

Example flow:

1. User requests a booking.
2. Toolkit validates the request.
3. Toolkit returns a preview and `confirmation_id`.
4. User approves the action.
5. Agent calls `confirm_operation`.
6. Toolkit executes the action.

This approach reduces ambiguity and mirrors approval workflows commonly used in production systems.

Pending confirmations will expire after five minutes to prevent outdated approvals from being executed later when operational conditions may have changed.

## Validation Strategy

Validation is pushed into schemas whenever possible.

Examples include:

- Minimum search term length.
- Non-negative stock quantities.
- Required carrier names.
- Valid exception categories.

This means invalid requests are rejected before business logic executes, reducing code complexity and making behaviour more predictable.

## Error Handling

The toolkit avoids generic error messages.

Every error response includes:

```json
{
  "error": true,
  "code": "ERROR_CODE",
  "message": "Human-readable explanation",
  "hint": "How to fix the issue",
  "suggested_call": {}
}
```

The intention is to give both users and agents enough information to understand the problem and recover without unnecessary back-and-forth.

## Tool Implementation Approach

Read-only tools return information without altering state.

Examples:

- `get_stock`
- `search_stock`
- `list_dock_slots`
- `list_open_exceptions`

State-changing tools generate a confirmation request first.

Examples:

- `request_dock_booking`
- `request_dock_cancellation`
- `adjust_stock_count`
- `move_stock`
- `raise_exception`
- `close_exception`

Execution happens only through:

- `confirm_operation`

Keeping all write operations behind a common confirmation mechanism makes behaviour consistent across the toolkit.

## Site Isolation

Site isolation is one of the most important requirements in this project.

To prevent accidental cross-site access:

1. The server is started with a fixed site configuration.
2. Only data for that site is loaded.
3. No tool accepts a site parameter.
4. Resources from other sites appear as unavailable rather than exposing information.

This design directly addresses the operational issue described by Ops and makes cross-site access structurally impossible.

## Testing Strategy

Testing focuses on the behaviours explicitly called out in the assessment criteria.

Where possible, tests call tool handlers directly rather than running a full MCP transport. This keeps the test suite fast while still validating business rules and tool behaviour.

The test suite will cover:

- Tool invocation
- Schema rejection
- Site scoping
- Confirmation workflows
- Error response structure
- Ambiguous lookups requiring clarification

Particular attention will be given to scenarios where the agent must ask a question instead of guessing.

For example, searching for "pallet wrap" should return multiple candidates and explicitly indicate that clarification is required.

## Agent Host Demonstration

After implementation, the server will be registered in a real MCP-compatible agent host.

The demonstration transcript should show the agent:

- Selecting tools dynamically.
- Handling successful lookups.
- Asking clarifying questions for ambiguous searches.
- Following the confirmation workflow.
- Respecting site boundaries.
- Recovering from invalid requests using actionable error feedback.

The transcript will be saved alongside the project deliverables.

## Non-Goals

This project intentionally does not implement fuzzy ranking or automatic best-match selection.

The stock dataset contains several near-identical products that differ by only one attribute. Returning a single "best" result would encourage confident mistakes.

Instead, the toolkit surfaces ambiguity and allows the user to make the final choice when multiple valid matches exist.

## Expected Deliverables

The final submission will include:

- Working MCP server
- Registration configuration
- Agent transcript
- Test suite with passing results
- Design rationale in `spec.md`
- Reflection document
- Effort statement

The overall aim is to demonstrate not only that the tools work, but that they are designed in a way that an agent can use safely and effectively.
