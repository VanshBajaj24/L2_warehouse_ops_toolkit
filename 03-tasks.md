# Tasks — Kestrel Warehouse MCP Toolkit

This document turns the implementation plan into a practical set of build tasks.

The work is organised into phases so that each layer of the system is built on a stable foundation. The goal is not only to create working MCP tools, but to create a toolkit that an agent can use safely, reliably, and predictably in a real warehouse environment.

Each task includes a clear success criterion so it is obvious when the work is complete and it's safe to move on to the next step.

---

# Phase 1: Project Foundation

Before implementing warehouse functionality, set up the project structure, dependencies, and shared utilities that the rest of the toolkit will depend on.

## Task 1: Set up the project

Create the initial project structure and install all required dependencies.

### Success criteria

- `pip install -e .` completes successfully
- `pytest --collect-only` runs without import errors

## Task 2: Create the shared error system

All tools should return errors in a consistent, actionable format.

### Success criteria

- ToolError supports code, message, hint, and suggested_call
- Standard error response matches the specification

## Task 3: Create input schemas

Define all MCP tool inputs using Pydantic models.

### Success criteria

- Invalid inputs raise ValidationError
- Valid inputs are accepted
- Schema constraints are enforced automatically

---

# Phase 2: Warehouse Data and State Management

## Task 4: Build read-only warehouse operations

Implement get_stock, search_stock, list_dock_slots, and list_open_exceptions.

### Success criteria

- Same-site lookups return correct results
- Cross-site data remains inaccessible

## Task 5: Build state-changing warehouse operations

Implement dock bookings, cancellations, stock adjustments, stock moves, and exception workflows.

### Success criteria

- Updates are reflected in subsequent reads
- Invalid requests return correct errors

## Task 6: Build the confirmation workflow

Create a reusable confirmation mechanism for all state-changing actions.

### Success criteria

- Confirmation IDs are generated
- Expired and duplicate confirmations are rejected

---

# Phase 3: MCP Server Implementation

## Task 7: Connect everything through the MCP server

Register all tools and expose them through MCP.

### Success criteria

- Server starts successfully
- Agent can discover registered tools

---

# Phase 4: Validate the System

## Task 8: Create shared test fixtures

### Success criteria

- Test discovery succeeds
- Fixtures are reusable across modules

## Task 9: Verify tool behaviour

### Success criteria

- Read-only and write operations behave as expected

## Task 10: Verify schema validation

### Success criteria

- Invalid requests never reach business logic

## Task 11: Verify site isolation

### Success criteria

- Cross-site access is blocked
- Same-site access works correctly

## Task 12: Verify confirmation behaviour

### Success criteria

- Confirmation lifecycle works correctly

## Task 13: Verify error consistency

### Success criteria

- Every tool returns the standard error shape

## Task 14: Verify ambiguity handling

### Success criteria

- Multiple matches trigger clarification instead of guessing

---

# Phase 5: Agent Integration and Submission Material

## Task 15: Register the MCP server with an agent host

### Success criteria

- Agent can see and invoke warehouse tools

## Task 16: Capture a real agent session

### Success criteria

- Transcript demonstrates tool usage, clarification, confirmation, and error recovery

## Task 17: Write the reflection

### Success criteria

- REFLECTION.md and effort statement are complete

---

# Definition of Done

The project is complete when all tools are implemented, tested, integrated with an agent host, and supported by transcripts and documentation.
