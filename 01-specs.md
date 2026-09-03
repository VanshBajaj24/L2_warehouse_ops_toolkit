# Kestrel Warehouse MCP Toolkit — Tool Interface Specification

> This document defines the tool interfaces for the Kestrel Warehouse agent toolkit.
> It was written before any implementation, based on analysis of the Ops requirements
> (`data/tool_specification.md`), the stock data (`data/stock_snapshot.csv`), and the
> dock schedule (`data/dock_schedule.jsonl`). Where the Ops request would produce a
> design that an agent uses badly, this spec departs from it and records why.

---

## Design Principles

1. **Read/write separation** — Every tool is either read-only or state-changing, never
   both. Read-only tools use `get_`/`search_`/`list_` prefixes. State-changing tools
   use action verbs (`book`, `cancel`, `adjust`, `move`, `raise`, `close`). This lets
   the model distinguish safe exploration from irreversible action.

2. **Site scoping at the server level** — The MCP server is configured with a single
   `site_id` at startup (environment variable `WAREHOUSE_SITE`). All data access and
   writes are scoped to that site. No tool accepts a site parameter. Cross-site access
   is structurally impossible, not merely validated.

3. **Ambiguity surfacing** — When data supports multiple plausible matches, all
   candidates are returned. The agent must present them to the user rather than
   picking one on their behalf.

4. **Two-step confirmation** — State-changing tools never execute on first call. They
   validate inputs and return a preview with a `confirmation_id`. A separate
   `confirm_operation` tool must be called with that ID to execute. This makes it
   structurally impossible to skip the preview — the model cannot execute without first
   obtaining a confirmation ID from the preview step. Irreversible operations flag
   `irreversible: true` in the preview.

5. **Actionable errors** — Every error includes a machine-readable `code`, a
   human-readable `message`, and a `hint` telling the model how to fix the call.

---

## Site Scoping

The server is initialized with one of three valid site IDs:

- `LEEDS-01`
- `READING-02`
- `GLASGOW-03`

This is set by the deployment environment, not by the agent or user.

- Read tools return only data for the configured site.
- Write tools reject any SKU or resource not belonging to the configured site.
- No tool exposes a site parameter.

**Evidence**: Ops reported an incident where a Leeds user accessed Reading's stock
numbers and quoted them to a customer. A site parameter would trust the caller to
supply the correct value — the same failure mode. Server-level binding makes cross-site
access structurally impossible: there is no parameter to supply the wrong value for.

---

## Error Shape (all tools)

```json
{
  "error": true,
  "code": "DESCRIPTIVE_ERROR_CODE",
  "message": "Human-readable explanation of what went wrong.",
  "hint": "What the caller should do differently to succeed."
}
```

`code` is a stable string identifier the model can branch on.
`hint` gives the model enough information to self-correct without human help.

---

## Confirmation Flow

All state-changing tools follow a two-step pattern:

**Step 1 — Request**: Call the state-changing tool with its parameters. The tool
validates inputs and returns a preview of the action along with a `confirmation_id`.
It does NOT execute.

```json
{
  "confirmation_id": "CONF-a1b2c3",
  "action": "book_dock_slot",
  "preview": "Book dock slot 10:00 on 2026-04-08 at LEEDS-01 for 'ABC Logistics'.",
  "requires_confirmation": true
}
```

For irreversible operations, the preview also includes `"irreversible": true`.

**Step 2 — Confirm**: After the user approves, call `confirm_operation` with the
`confirmation_id`. The toolkit executes the action and returns the result.

```json
confirm_operation(confirmation_id="CONF-a1b2c3")
```

Confirmation IDs expire after 5 minutes to prevent stale operations from executing
against changed data.

**Why not a `confirmed` boolean?** A boolean parameter on each tool trusts the model
not to pass `true` on the first call. A separate confirmation tool makes skipping the
preview structurally impossible — the model must obtain the confirmation ID from the
preview response before it can execute.

---

## Tool Definitions

### 1. `get_stock` — read-only

**Model-facing description**:
> Retrieve a single stock item by its exact SKU code. Returns the item's description,
> bin location, quantity, and unit. Use this when the user provides a full SKU
> (e.g., "SKU-8801"). If the SKU is unknown, use `search_stock` instead.

**Parameters**:

| Name  | Type   | Required | Description                          |
|-------|--------|----------|--------------------------------------|
| `sku` | string | yes      | Exact SKU code (e.g., `"SKU-8801"`). |

**Success response**:
```json
{
  "sku": "SKU-8801",
  "description": "Pallet wrap, 500mm clear",
  "bin": "A-12-3",
  "quantity": 240,
  "unit": "each"
}
```

**Errors**:

| Code                | When                                      | Hint                                                                  |
|---------------------|-------------------------------------------|-----------------------------------------------------------------------|
| `SKU_NOT_FOUND`     | No item with that SKU at this site.       | `"Use search_stock with a description keyword to find the correct SKU."` |
| `INVALID_SKU_FORMAT`| SKU doesn't match pattern `SKU-NNNN`.    | `"SKU codes follow the pattern SKU-NNNN (e.g., SKU-8801)."`           |

---

### 2. `search_stock` — read-only

**Model-facing description**:
> Search stock items by description keyword. Returns ALL matching items at this site —
> do not assume the first result is correct. If multiple items match, present every
> candidate to the user and ask which one they mean. If only one matches, you may
> proceed with it. Use this when the user describes a product by name rather than SKU.

**Parameters**:

| Name    | Type   | Required | Description                                                   |
|---------|--------|----------|---------------------------------------------------------------|
| `query` | string | yes      | Keyword to match against descriptions (case-insensitive, substring). Minimum 2 characters. |

**Success response**:
```json
{
  "matches": [
    {
      "sku": "SKU-8801",
      "description": "Pallet wrap, 500mm clear",
      "bin": "A-12-3",
      "quantity": 240,
      "unit": "each"
    },
    {
      "sku": "SKU-8802",
      "description": "Pallet wrap, 500mm black",
      "bin": "A-12-4",
      "quantity": 180,
      "unit": "each"
    }
  ],
  "total": 2
}
```

**Errors**:

| Code              | When                              | Hint                                                                |
|-------------------|-----------------------------------|---------------------------------------------------------------------|
| `NO_MATCHES`      | No items match the query.         | `"Try a broader keyword, or use get_stock if you have the exact SKU."` |
| `QUERY_TOO_SHORT` | Query is fewer than 2 characters. | `"Provide a longer search term (minimum 2 characters)."`             |

**Design rationale — why two lookup tools**:
The stock data contains eight near-duplicate pairs that differ by a single word:

| SKU pair        | Descriptions                                          |
|-----------------|-------------------------------------------------------|
| 8801 / 8802     | Pallet wrap, 500mm **clear** vs **black**             |
| 8803 / 8804     | Strapping band, **12mm** vs **16mm**                  |
| 8805 / 8806     | Corner protector, **50mm** vs **75mm**                |
| 8808 / 8809     | Shrink film, **400mm** vs **600mm**                   |
| 8810 / 8811     | Void fill, **paper** vs **air pillow**                |
| 8812 / 8813     | Tape, 48mm **clear** vs **printed**                   |
| 8815 / 8816     | Pallet, **standard UK** vs **euro**                   |

A single fuzzy lookup returning a "best match" would confidently return the wrong item
in at least half these cases (e.g., searching "pallet wrap" would pick one of two valid
results). Splitting into exact-SKU lookup (`get_stock`) and keyword search
(`search_stock` returning all candidates) means:

- An exact SKU lookup has a definite answer (0 or 1).
- A description search surfaces all candidates so the agent can disambiguate when needed.
- When only one item matches (e.g., "air pillow" at LEEDS-01), no unnecessary
  disambiguation is forced — the agent sees `total: 1` and can proceed.

---

### 3. `list_dock_slots` — read-only

**Model-facing description**:
> List dock slots for a given date at this site. Optionally filter by status. Use this
> to check availability before booking, or to show the user the current schedule.
> This is read-only — to book or cancel, use `book_dock_slot` or `cancel_dock_booking`.

**Parameters**:

| Name     | Type   | Required | Description                                              |
|----------|--------|----------|----------------------------------------------------------|
| `date`   | string | yes      | Date to check, format `YYYY-MM-DD`.                      |
| `status` | enum: `"available"`, `"booked"` | no | Filter by slot status. Omit to return all slots. |

**Success response**:
```json
{
  "site": "LEEDS-01",
  "date": "2026-04-08",
  "slots": [
    { "slot": "06:00", "status": "available", "carrier": null },
    { "slot": "08:00", "status": "booked", "carrier": "Northbound Freight" },
    { "slot": "10:00", "status": "available", "carrier": null }
  ]
}
```

**Errors**:

| Code                  | When                              | Hint                                                    |
|-----------------------|-----------------------------------|---------------------------------------------------------|
| `INVALID_DATE_FORMAT` | Date is not `YYYY-MM-DD`.         | `"Reformat the date as YYYY-MM-DD (e.g., 2026-04-08)."` |
| `INVALID_STATUS`      | Status is not a valid enum value. | `"Valid values: \"available\", \"booked\"."` |

**Design rationale — why three dock tools instead of one**:
Ops asked for one `check_dock` tool that checks availability, books, and cancels. This
conflates reading with writing through a single tool name. An agent calling `check_dock`
to see what's free cannot accidentally trigger a booking. Split into:
- `list_dock_slots` (read-only) — safe to call at any time
- `book_dock_slot` (state-changing) — clearly a write, requires confirmation
- `cancel_dock_booking` (state-changing) — clearly a write, requires confirmation

---

### 4. `list_open_exceptions` — read-only

**Model-facing description**:
> List all open (unresolved) exception tickets at this site. Use this to discover
> exception IDs before closing them with `close_exception`, or to show the user what
> issues are currently outstanding.

**Parameters**:

| Name  | Type   | Required | Description                                                        |
|-------|--------|----------|--------------------------------------------------------------------|
| `sku` | string | no       | Filter exceptions by SKU. Omit to list all open exceptions at this site. |

**Success response**:
```json
{
  "site": "LEEDS-01",
  "open_exceptions": [
    {
      "exception_id": "EXC-20260408-001",
      "sku": "SKU-8801",
      "category": "damaged",
      "description": "Three rolls found crushed under shifted pallet",
      "raised_at": "2026-04-08T09:15:00Z"
    }
  ],
  "total": 1
}
```

**Errors**:

| Code            | When                                       | Hint                                                 |
|-----------------|--------------------------------------------|------------------------------------------------------|
| `SKU_NOT_FOUND` | Filtered SKU does not exist at this site.  | `"Use search_stock to find the correct SKU."`        |

**Design rationale — why this tool was added**:
Ops did not request this, but without it the agent has no way to discover which
exceptions exist. An agent asked to "close the exception for the damaged pallet wrap"
would need to already know the exception ID. `list_open_exceptions` lets the agent
look up open tickets by SKU or list them all, then pass the correct ID to
`close_exception`. This is also the only way for an Ops user to get a view of
outstanding issues at their site.

---

### 5. `book_dock_slot` — state-changing, requires confirmation

**Model-facing description**:
> Book an available dock slot for a carrier. This tool validates the request and returns
> a preview with a confirmation_id. To execute the booking, pass the confirmation_id to
> `confirm_operation` after the user approves. Only books slots at this site.

**Parameters**:

| Name      | Type   | Required | Description                                                       |
|-----------|--------|----------|-------------------------------------------------------------------|
| `date`    | string | yes      | Date of the slot, format `YYYY-MM-DD`.                            |
| `slot`    | enum: `"06:00"`, `"08:00"`, `"10:00"`, `"12:00"`, `"14:00"`, `"16:00"` | yes | Time slot to book. |
| `carrier` | string | yes      | Name of the carrier (minimum 1 character).                        |

**Preview response** (always returned — tool never executes directly):
```json
{
  "confirmation_id": "CONF-a1b2c3",
  "action": "book_dock_slot",
  "preview": "Book dock slot 10:00 on 2026-04-08 at LEEDS-01 for 'ABC Logistics'.",
  "requires_confirmation": true
}
```

**Execution response** (returned by `confirm_operation`):
```json
{
  "action": "book_dock_slot",
  "executed": true,
  "date": "2026-04-08",
  "slot": "10:00",
  "carrier": "ABC Logistics",
  "message": "Dock slot booked successfully."
}
```

**Errors**:

| Code                 | When                                      | Hint                                                        |
|----------------------|-------------------------------------------|-------------------------------------------------------------|
| `SLOT_ALREADY_BOOKED`| The slot is already booked.               | `"Use list_dock_slots to find an available slot."`           |
| `INVALID_SLOT_TIME`  | Slot time not in the valid set.           | `"Valid slot times: 06:00, 08:00, 10:00, 12:00, 14:00, 16:00."` |
| `INVALID_DATE_FORMAT`| Date is not `YYYY-MM-DD`.                 | `"Reformat the date as YYYY-MM-DD (e.g., 2026-04-08)."`     |

---

### 6. `cancel_dock_booking` — state-changing, requires confirmation

**Model-facing description**:
> Cancel an existing dock booking. Returns a preview with a confirmation_id. Pass the
> confirmation_id to `confirm_operation` after the user approves. Use when a carrier
> no-shows or a booking needs to be released.

**Parameters**:

| Name   | Type   | Required | Description                                                              |
|--------|--------|----------|--------------------------------------------------------------------------|
| `date` | string | yes      | Date of the booking, format `YYYY-MM-DD`.                                |
| `slot` | enum: `"06:00"`, `"08:00"`, `"10:00"`, `"12:00"`, `"14:00"`, `"16:00"` | yes | Time slot to cancel. |

**Preview response**:
```json
{
  "confirmation_id": "CONF-d4e5f6",
  "action": "cancel_dock_booking",
  "preview": "Cancel booking for 'Northbound Freight' at slot 08:00 on 2026-04-08 at LEEDS-01.",
  "requires_confirmation": true
}
```

**Execution response** (returned by `confirm_operation`):
```json
{
  "action": "cancel_dock_booking",
  "executed": true,
  "date": "2026-04-08",
  "slot": "08:00",
  "previous_carrier": "Northbound Freight",
  "message": "Booking cancelled. Slot is now available."
}
```

**Errors**:

| Code                  | When                          | Hint                                                 |
|-----------------------|-------------------------------|------------------------------------------------------|
| `SLOT_NOT_BOOKED`     | The slot has no booking.      | `"Use list_dock_slots to see current bookings."`     |
| `INVALID_SLOT_TIME`   | Same as `book_dock_slot`.     | Same as `book_dock_slot`.                            |
| `INVALID_DATE_FORMAT` | Same as above.                | Same as above.                                       |

---

### 7. `adjust_stock_count` — state-changing, requires confirmation, IRREVERSIBLE

**Model-facing description**:
> Correct the recorded quantity of a stock item. This creates an audit record that feeds
> the month-end count and CANNOT be undone — even a reversal creates a second audit
> entry, it does not erase the first. Returns a preview with a confirmation_id. Pass
> the confirmation_id to `confirm_operation` after confirming the new quantity with the
> user. Do not use this for bin moves — use `move_stock` instead.

**Parameters**:

| Name           | Type    | Required | Description                                               |
|----------------|---------|----------|-----------------------------------------------------------|
| `sku`          | string  | yes      | The SKU to adjust.                                        |
| `new_quantity` | integer | yes      | The corrected quantity (>= 0).                            |
| `reason`       | string  | yes      | Why the count is being corrected (written to audit trail). |

**Preview response**:
```json
{
  "confirmation_id": "CONF-g7h8i9",
  "action": "adjust_stock_count",
  "preview": "Adjust SKU-8801 ('Pallet wrap, 500mm clear') at bin A-12-3: 240 → 235 each. Reason: 'Five units found damaged during count'.",
  "irreversible": true,
  "requires_confirmation": true
}
```

**Execution response** (returned by `confirm_operation`):
```json
{
  "action": "adjust_stock_count",
  "executed": true,
  "sku": "SKU-8801",
  "previous_quantity": 240,
  "new_quantity": 235,
  "unit": "each",
  "reason": "Five units found damaged during count",
  "message": "Stock count adjusted. This adjustment will appear in the month-end count."
}
```

**Errors**:

| Code                | When                                | Hint                                                       |
|---------------------|-------------------------------------|------------------------------------------------------------|
| `SKU_NOT_FOUND`     | No item with that SKU at this site. | `"Use search_stock to find the correct SKU at this site."` |
| `NEGATIVE_QUANTITY` | `new_quantity` is < 0.              | `"Quantity must be zero or a positive integer."`           |
| `MISSING_REASON`    | `reason` is empty or absent.        | `"A reason is required for the audit trail."`              |

**Design rationale — why stock adjustment and bin move are separate tools**:
Ops described corrections and moves as "the same kind of thing." They are not:

- A **count correction** changes `quantity`, creates an audit entry that feeds month-end
  reconciliation, and is effectively irreversible. The parameters are SKU + new quantity
  + reason.
- A **bin move** changes `bin` location without affecting total quantity. The parameters
  are SKU + from_bin + to_bin + quantity to move.

Combining them in one `stock_change` tool would force the model to pick between two
unrelated operations through a mode parameter. The confirmation preview could not
clearly communicate that one path is irreversible and the other is not. Worse, a model
that confuses the modes could record an audit-trail correction when the user only wanted
to update a bin location.

---

### 8. `move_stock` — state-changing, requires confirmation

**Model-facing description**:
> Record a bin-to-bin move of stock within this site. This changes the item's location
> but does not alter total quantity. Returns a preview with a confirmation_id. Pass the
> confirmation_id to `confirm_operation` after the user approves.
> Use `adjust_stock_count` if the quantity itself is wrong.

**Parameters**:

| Name       | Type    | Required | Description                                             |
|------------|---------|----------|---------------------------------------------------------|
| `sku`      | string  | yes      | The SKU to move.                                        |
| `from_bin` | string  | yes      | Current bin (must match the item's recorded location).  |
| `to_bin`   | string  | yes      | Destination bin.                                        |
| `quantity` | integer | yes      | Number of units to move (> 0).                          |

**Preview response**:
```json
{
  "confirmation_id": "CONF-j1k2l3",
  "action": "move_stock",
  "preview": "Move 50 each of SKU-8801 ('Pallet wrap, 500mm clear') from bin A-12-3 to bin A-15-1.",
  "requires_confirmation": true
}
```

**Execution response** (returned by `confirm_operation`):
```json
{
  "action": "move_stock",
  "executed": true,
  "sku": "SKU-8801",
  "from_bin": "A-12-3",
  "to_bin": "A-15-1",
  "quantity_moved": 50,
  "remaining_in_source": 190,
  "message": "Stock move recorded."
}
```

**Errors**:

| Code                 | When                                                 | Hint                                                           |
|----------------------|------------------------------------------------------|----------------------------------------------------------------|
| `SKU_NOT_FOUND`      | No item with that SKU at this site.                  | `"Use search_stock to find the correct SKU."`                  |
| `BIN_MISMATCH`       | Item is not in the specified source bin.             | `"Use get_stock to check the current bin for this SKU."`       |
| `INSUFFICIENT_STOCK` | Not enough units in the source bin.                  | `"Only N units available in that bin."`                        |
| `SAME_BIN`           | Source and destination are the same bin.             | `"Provide a different destination bin."`                       |

---

### 9. `raise_exception` — state-changing, requires confirmation

**Model-facing description**:
> Open an exception ticket for a stock problem (damaged, missing, etc.). Returns a
> preview with a confirmation_id. Pass the confirmation_id to `confirm_operation`
> after the user approves. The execution response includes an exception ID that can
> later be passed to `close_exception`.

**Parameters**:

| Name          | Type   | Required | Description                              |
|---------------|--------|----------|------------------------------------------|
| `sku`         | string | yes      | The SKU the exception relates to.        |
| `category`    | enum: `"damaged"`, `"missing"`, `"wrong_item"`, `"contaminated"`, `"other"` | yes | Type of exception. |
| `description` | string | yes      | Brief description of the problem.        |

**Preview response**:
```json
{
  "confirmation_id": "CONF-m4n5o6",
  "action": "raise_exception",
  "preview": "Raise 'damaged' exception for SKU-8801 ('Pallet wrap, 500mm clear'): 'Three rolls found crushed under shifted pallet'.",
  "requires_confirmation": true
}
```

**Execution response** (returned by `confirm_operation`):
```json
{
  "action": "raise_exception",
  "executed": true,
  "exception_id": "EXC-20260408-001",
  "sku": "SKU-8801",
  "category": "damaged",
  "description": "Three rolls found crushed under shifted pallet",
  "status": "open",
  "message": "Exception raised. Use close_exception with ID 'EXC-20260408-001' when resolved."
}
```

**Errors**:

| Code               | When                                 | Hint                                                              |
|--------------------|--------------------------------------|-------------------------------------------------------------------|
| `SKU_NOT_FOUND`    | No item with that SKU at this site.  | `"Use search_stock to find the correct SKU."`                     |
| `INVALID_CATEGORY` | Category not in the valid set.       | `"Valid categories: damaged, missing, wrong_item, contaminated, other."` |

---

### 10. `close_exception` — state-changing, requires confirmation

**Model-facing description**:
> Close an open exception ticket with a resolution note. Returns a preview with a
> confirmation_id. Pass the confirmation_id to `confirm_operation` after the user
> approves. Once closed, an exception cannot be reopened — if the issue recurs,
> raise a new exception.

**Parameters**:

| Name           | Type   | Required | Description                                              |
|----------------|--------|----------|----------------------------------------------------------|
| `exception_id` | string | yes      | The exception ID to close (e.g., `"EXC-20260408-001"`). |
| `resolution`   | string | yes      | What was done to resolve the issue.                      |

**Preview response**:
```json
{
  "confirmation_id": "CONF-p7q8r9",
  "action": "close_exception",
  "preview": "Close exception EXC-20260408-001 (damaged, SKU-8801) with resolution: 'Damaged units removed and stock count adjusted'.",
  "requires_confirmation": true
}
```

**Execution response** (returned by `confirm_operation`):
```json
{
  "action": "close_exception",
  "executed": true,
  "exception_id": "EXC-20260408-001",
  "status": "closed",
  "resolution": "Damaged units removed and stock count adjusted",
  "message": "Exception closed."
}
```

**Errors**:

| Code                  | When                                      | Hint                                                                      |
|-----------------------|-------------------------------------------|---------------------------------------------------------------------------|
| `EXCEPTION_NOT_FOUND` | No exception with that ID at this site.   | `"Use list_open_exceptions to find valid exception IDs."`                 |
| `ALREADY_CLOSED`      | The exception is already closed.          | `"This exception was already resolved. Raise a new one if the issue recurs."` |

---

### 11. `confirm_operation` — execution

**Model-facing description**:
> Execute a previously previewed state-changing operation. Every state-changing tool
> (book_dock_slot, cancel_dock_booking, adjust_stock_count, move_stock, raise_exception,
> close_exception) returns a confirmation_id in its preview. Pass that ID here after the
> user has approved the action. Confirmation IDs expire after 5 minutes.

**Parameters**:

| Name              | Type   | Required | Description                                                      |
|-------------------|--------|----------|------------------------------------------------------------------|
| `confirmation_id` | string | yes      | The confirmation ID from a state-changing tool's preview response. |

**Success response**: Returns the execution response of the original tool (see each
tool's "Execution response" above).

**Errors**:

| Code                      | When                                          | Hint                                                                  |
|---------------------------|-----------------------------------------------|-----------------------------------------------------------------------|
| `INVALID_CONFIRMATION_ID` | The ID does not match any pending operation.  | `"The confirmation ID is invalid. Call the original tool again to get a new preview."` |
| `CONFIRMATION_EXPIRED`    | The confirmation ID has expired (> 5 minutes).| `"The confirmation has expired. Call the original tool again to get a fresh preview."` |
| `ALREADY_CONFIRMED`       | The operation was already executed.           | `"This operation was already confirmed and executed."`                 |

**Design rationale**:
A `confirmed: boolean` parameter on each state-changing tool trusts the model not to
pass `true` on the first call, which would skip the preview. A separate confirmation
tool makes this structurally impossible — the model must first call the state-changing
tool (which only returns a preview), obtain the confirmation ID, present the preview to
the user, and then call `confirm_operation`. There is no shortcut.

---

## Tool Summary

| #  | Tool name              | Type            | Confirmation | Irreversible |
|----|------------------------|-----------------|--------------|--------------|
| 1  | `get_stock`            | read-only       | —            | —            |
| 2  | `search_stock`         | read-only       | —            | —            |
| 3  | `list_dock_slots`      | read-only       | —            | —            |
| 4  | `list_open_exceptions` | read-only       | —            | —            |
| 5  | `book_dock_slot`       | state-changing  | yes          | no           |
| 6  | `cancel_dock_booking`  | state-changing  | yes          | no           |
| 7  | `adjust_stock_count`   | state-changing  | yes          | **yes**      |
| 8  | `move_stock`           | state-changing  | yes          | no           |
| 9  | `raise_exception`      | state-changing  | yes          | no           |
| 10 | `close_exception`      | state-changing  | yes          | no           |
| 11 | `confirm_operation`    | execution       | —            | —            |

---

## Design Departures from Ops Request

| # | Ops asked for | We provide | Evidence and reasoning |
|---|---------------|------------|------------------------|
| 1 | `lookup` — one tool, fuzzy match | `get_stock` + `search_stock` | SKU-8801/8802 ("Pallet wrap, 500mm clear" vs "black"), SKU-8803/8804 ("Strapping band, 12mm" vs "16mm"), and six other pairs differ by a single word. A fuzzy best-match would confidently return the wrong item. Split: exact SKU lookup for definite answers, keyword search returning all candidates for disambiguation. When only one item matches (e.g., "air pillow" at LEEDS-01), the agent sees `total: 1` and proceeds without unnecessary disambiguation. |
| 2 | `check_dock` — one tool for read + book + cancel | `list_dock_slots` + `book_dock_slot` + `cancel_dock_booking` | Mixing read and write behind one name makes the model unable to distinguish safe exploration from state change. An agent calling a combined tool to "check" availability could accidentally trigger a booking if the mode parameter is wrong. Three separate tools with clear read/write semantics eliminate this risk. |
| 3 | `stock_change` — one tool for corrections and moves | `adjust_stock_count` + `move_stock` | Count corrections change quantity and feed month-end reconciliation (Ops: "Stock corrections feed the month-end count so they need to be right") — an irreversible audit entry. Bin moves change location only. Different parameters (new_quantity+reason vs from_bin+to_bin+quantity), different consequences (audit trail vs location update), different irreversibility. A combined tool with a mode switch would make the model unable to surface the irreversibility warning appropriately. |
| 4 | Site as implicit context | Site enforced at server level, no parameter on any tool | Ops: "someone at Leeds could see Reading's numbers and quoted them to a customer." A site parameter trusts the caller to supply the correct value. Server-level configuration (env var `WAREHOUSE_SITE`) makes cross-site access structurally impossible — there is no parameter to get wrong. |
| 5 | No confirmation flow mentioned | Two-step confirmation via `confirm_operation` tool | Ops said "stock corrections feed the month-end count" (irreversible), and dock bookings are visible to carriers. A `confirmed` boolean would trust the model not to skip the preview. A separate `confirm_operation` tool makes skipping structurally impossible — the model must obtain a confirmation ID from the preview first. |
| 6 | No way to discover exceptions | `list_open_exceptions` added | Without this, an agent asked to "close the damaged pallet wrap exception" has no way to discover the exception ID. This tool lets the agent look up open tickets by SKU or list all outstanding exceptions at the site. |
| 7 | `close_exception` without `reopen_exception` | Same — no reopen provided | Ops asked for close but not reopen. Reopening closed tickets creates ambiguous audit trails (was the resolution wrong, or is this a new occurrence?). Deliberate position: closed exceptions stay closed; recurrences get new tickets. If Ops later needs reopen, it should be a separate tool with its own confirmation flow. |

---

## Closed Value Sets (expressed as enums in schema)

| Parameter                       | Valid values                                                          |
|---------------------------------|-----------------------------------------------------------------------|
| `list_dock_slots.status`        | `"available"`, `"booked"`                                             |
| `book_dock_slot.slot`           | `"06:00"`, `"08:00"`, `"10:00"`, `"12:00"`, `"14:00"`, `"16:00"`     |
| `cancel_dock_booking.slot`      | `"06:00"`, `"08:00"`, `"10:00"`, `"12:00"`, `"14:00"`, `"16:00"`     |
| `raise_exception.category`      | `"damaged"`, `"missing"`, `"wrong_item"`, `"contaminated"`, `"other"` |
| Server config: `WAREHOUSE_SITE` | `"LEEDS-01"`, `"READING-02"`, `"GLASGOW-03"`                          |
