# Reflection — Kestrel Warehouse MCP Toolkit

## Looking Back on the Spec-First Approach

The biggest lesson from this project was how much value comes from slowing down and designing before writing code.

My initial instinct was to start building tools and wire them into an MCP server as quickly as possible. However, the requirement to write the specification first forced me to spend time understanding the data, the workflows, and the assumptions behind the Ops team's requests.

In hindsight, that probably saved more time than it cost.

### The stock lookup problem became obvious only after reading the data

One of the first things I noticed while reviewing `stock_snapshot.csv` was how many products looked almost identical.

For example:

- Pallet wrap, 500mm clear
- Pallet wrap, 500mm black

At first glance, a single lookup tool seemed perfectly reasonable. But after looking through the dataset, it became clear that a fuzzy search returning a "best match" would regularly return the wrong item with complete confidence.

That realization changed the design completely.

Instead of building one lookup tool, I split the functionality into:

- `get_stock` for exact SKU searches
- `search_stock` for keyword searches that return all possible matches

The important lesson here was that usability problems often appear in the data long before they appear in the code.

### Writing the interface exposed hidden differences

The second major insight came while documenting tool parameters.

The Ops requirements grouped stock corrections and stock moves together as if they were variations of the same action.

Once I started writing the parameter definitions, the difference became obvious.

A stock correction:

- Changes recorded quantity
- Creates an audit entry
- Affects reconciliation processes

A stock move:

- Changes location
- Does not affect quantity
- Does not require reconciliation

Although both actions involve inventory, they represent very different business events.

Designing them as separate tools keeps those differences visible and reduces the chance that an agent executes the wrong operation.

### The confirmation workflow improved before a single line of code was written

One of the most useful design changes happened during the specification phase.

My first version used a simple:

```json
{
  "confirmed": true
}
```

pattern.

The more I thought about it, the less comfortable I became with it. There was nothing preventing an agent from accidentally skipping the preview step and immediately executing an action.

The final design introduced:

```text
request_action(...)
```

followed by:

```text
confirm_operation(...)
```

using a generated confirmation ID.

This felt much closer to how production approval workflows work and turned a convention into an enforced workflow.

Making this change in the specification took minutes. Making it after implementation would have required touching handlers, tests, documentation, and transcripts.

## What I Would Improve in a Second Iteration

### Test the MCP layer directly

Most of the testing focuses on business logic through the `DataStore` and `ConfirmationStore`.

That gives strong confidence in the core behaviour, but it does not fully exercise the MCP integration layer.

A future version would include tests that call the actual MCP tools through a client and verify:

- Schema validation
- Tool registration
- Error conversion
- Confirmation routing

This would provide end-to-end coverage rather than just unit-level coverage.

### Make exception handling richer

The toolkit includes:

- `raise_exception`
- `close_exception`
- `list_open_exceptions`

However, there is no dedicated:

```text
get_exception
```

tool.

Adding a dedicated exception lookup would make the workflow cleaner.

### Strengthen date validation

The current design validates date format, but not necessarily date correctness.

For example:

```text
2026-02-30
```

matches the expected format even though it is not a valid calendar date.

Using proper date parsing would make the toolkit more robust.

## The Hardest Design Decision

The most difficult decision involved the `move_stock` operation.

I spent quite a bit of time deciding whether the agent should provide the source bin or whether the toolkit should determine it automatically.

Ultimately, I chose to require `from_bin` because it acts as a safety check and helps identify stale assumptions instead of silently proceeding with potentially incorrect information.

That choice aligned with the broader philosophy of the project: verify assumptions rather than trust them.

## Other Decisions I Am Happy With

### Showing out-of-stock items

I deliberately chose to return products even when their quantity is zero.

If an item exists but is out of stock, saying “No item found” is misleading. Returning the item with a quantity of zero gives users a more accurate picture of warehouse inventory.

### Removing site parameters entirely

Rather than validating site parameters, I removed them entirely.

The server is bound to a single site and only loads data for that site. This makes cross-site access impossible rather than merely discouraged.

### Expiring confirmations

The five-minute confirmation timeout felt like a reasonable compromise.

It gives warehouse operators enough time to review an action while reducing the risk of stale approvals being executed later.

### Keeping exceptions closed

I intentionally did not create a `reopen_exception` tool.

If the same issue occurs again later, creating a new exception produces a clearer audit trail than reopening an old one.

## Final Thoughts

The most valuable takeaway from this exercise was that good tool design is often more important than tool implementation.

Building a working MCP server was relatively straightforward. The harder and more interesting challenge was deciding what the tools should look like in the first place.

The final result is not just a collection of MCP tools. It is a toolkit designed to help an agent make safer decisions, ask better questions when information is ambiguous, and avoid accidental operational mistakes.

## Declared Effort Statement

This submission was completed with assistance from AI tools during design, implementation, and documentation.

All design decisions were reviewed and validated against the provided requirements and datasets before implementation.

**Approximate active effort:** 14–15 hours, including specification design, implementation, testing, and transcript preparation.
