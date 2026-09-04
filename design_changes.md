# Design Changes from Ops Request — With Reasoning

This document lists every departure from the Ops-requested tool design
(`data/tool_specification.md`), along with the data or requirement that drove each
decision.

---

## 1. `lookup` → split into `get_stock` + `search_stock`

**What Ops asked for**: A single `lookup` tool — "Just let me ask about a product and
get back where it is and how many we have. Sometimes I know the SKU, sometimes I only
know roughly what it's called."

**What we built**: Two separate tools:
- `get_stock` — exact SKU lookup, returns 0 or 1 result.
- `search_stock` — keyword search, returns ALL matches.

**Reasoning**: The stock data contains eight near-duplicate pairs that differ by one word:

| SKU pair    | Descriptions                                      |
|-------------|---------------------------------------------------|
| 8801 / 8802 | Pallet wrap, 500mm **clear** vs **black**         |
| 8803 / 8804 | Strapping band, **12mm** vs **16mm**              |
| 8805 / 8806 | Corner protector, **50mm** vs **75mm**             |
| 8808 / 8809 | Shrink film, **400mm** vs **600mm**                |
| 8810 / 8811 | Void fill, **paper** vs **air pillow**             |
| 8812 / 8813 | Tape, 48mm **clear** vs **printed**                |
| 8815 / 8816 | Pallet, **standard UK** vs **euro**                |

A single fuzzy lookup returning a "best match" would confidently return the wrong item
in at least half these cases. Searching "pallet wrap" picks one of two valid results —
and the wrong choice gets quoted to a customer.

Split design means:
- Exact SKU → definite answer (0 or 1).
- Keyword search → all candidates surfaced, agent disambiguates when `total > 1`.
- When only one item matches (e.g., "air pillow" at LEEDS-01, `total: 1`), no
  unnecessary disambiguation is forced.

---

## 2. `check_dock` → split into `list_dock_slots` + `book_dock_slot` + `cancel_dock_booking`

**What Ops asked for**: One `check_dock` tool — "Show me what dock slots are free. Also
I need to be able to book one, and cancel one if the carrier no-shows."

**What we built**: Three tools:
- `list_dock_slots` (read-only)
- `book_dock_slot` (state-changing, requires confirmation)
- `cancel_dock_booking` (state-changing, requires confirmation)

**Reasoning**: Mixing read and write behind one tool name makes the model unable to
distinguish safe exploration from state change. An agent calling `check_dock` to "see
what's free" could accidentally trigger a booking if a mode parameter is wrong. Three
separate tools with clear read/write semantics eliminate this risk. The tool naming
convention (`list_` prefix = safe to call anytime, action verbs = state change) lets the
model reason about safety without reading descriptions.

---

## 3. `stock_change` → split into `adjust_stock_count` + `move_stock`

**What Ops asked for**: One `stock_change` tool — "When a count is wrong I need to
correct it. And when we move something between bins I need to record that too. It's the
same kind of thing really."

**What we built**: Two tools:
- `adjust_stock_count` (state-changing, irreversible, requires confirmation)
- `move_stock` (state-changing, requires confirmation)

**Reasoning**: These are not the same kind of thing:

| Aspect              | Count correction         | Bin move                     |
|---------------------|--------------------------|------------------------------|
| What changes        | quantity                 | bin location                 |
| Parameters          | sku, new_quantity, reason| sku, from_bin, to_bin, quantity |
| Audit impact        | Feeds month-end count    | Location update only         |
| Reversibility       | **Irreversible** (audit entry persists) | Reversible (move back)  |

Ops said "Stock corrections feed the month-end count so they need to be right."
Combining them behind a mode switch would make the model unable to surface the
irreversibility warning for corrections while keeping moves lightweight. A model that
confuses the modes could record an audit-trail correction when the user only wanted to
move stock between bins.

---

## 4. Site as implicit context → site enforced at server level

**What Ops described**: Site as background context — staff are assigned to one site.

**What we built**: The MCP server is configured with a single `site_id` via environment
variable (`WAREHOUSE_SITE`). No tool accepts a site parameter. Data for other sites is
never loaded into memory.

**Reasoning**: Ops reported: "We had a problem last year where someone at Leeds could
see Reading's numbers and quoted them to a customer." A site parameter trusts the caller
to supply the correct value — the same failure mode. Server-level binding makes
cross-site access structurally impossible: there is no parameter to supply the wrong
value for.

Error messages do not reveal that a SKU exists at another site — they simply report
"No stock item with SKU 'X' at this site."

---

## 5. No confirmation flow → two-step confirmation via `confirm_operation`

**What Ops asked for**: Nothing — "they want everything to be fast."

**What we built**: All state-changing tools return a preview with a `confirmation_id`.
A separate `confirm_operation` tool must be called to execute. Confirmation IDs expire
after 5 minutes. Irreversible operations flag `irreversible: true` in the preview.

**Reasoning**: Ops said "Stock corrections feed the month-end count so they need to be
right." Dock bookings are visible to carriers. Ops "were not asked about which of these
actions should be reversible. That is your problem, not theirs."

A `confirmed: boolean` parameter on each tool would trust the model not to pass `true`
on the first call. A separate `confirm_operation` tool makes skipping the preview
structurally impossible — the model must obtain a confirmation ID from the preview before
it can execute.

---

## 6. Added `list_open_exceptions` (not requested by Ops)

**What Ops asked for**: `raise_exception` and `close_exception` only.

**What we built**: Added `list_open_exceptions` as a read-only tool to discover open
exception IDs, optionally filtered by SKU.

**Reasoning**: Without this, an agent asked to "close the exception for the damaged
pallet wrap" has no way to discover the exception ID. The agent would need the user to
remember and provide the exact ID. `list_open_exceptions` lets the agent look up open
tickets autonomously and pass the correct ID to `close_exception`.

---

## 7. No `reopen_exception` (Ops asked for close but not reopen)

**What Ops asked for**: `close_exception` — "And close it when it's sorted."

**What we built**: Same — close only. No reopen capability.

**Reasoning**: Ops asked for close but not reopen. Reopening closed tickets creates
ambiguous audit trails — was the resolution wrong, or is this a new occurrence of the
same problem? Deliberate position: closed exceptions stay closed; if the issue recurs,
a new exception is raised. If Ops later requests reopening, it should be added as a
separate tool with its own confirmation flow rather than bolted onto `close_exception`.
