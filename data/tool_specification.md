# Kestrel Warehouse - Requested Agent Tools (Synthetic)

> Drafted by the Warehouse Ops team, not by engineers. This is what they asked for,
> in their words. It is a requirements document, not a design.

Ops staff want an assistant that can answer stock and dock questions and raise
exceptions, so they stop switching between three systems on a forklift terminal.

Three sites: LEEDS-01, READING-02, GLASGOW-03. Staff are assigned to one site.

## What they asked for

### 1. `lookup`

> "Just let me ask about a product and get back where it is and how many we have.
> Sometimes I know the SKU, sometimes I only know roughly what it's called."

### 2. `check_dock`

> "Show me what dock slots are free. Also I need to be able to book one, and
> cancel one if the carrier no-shows."

### 3. `stock_change`

> "When a count is wrong I need to correct it. And when we move something between
> bins I need to record that too. It's the same kind of thing really."

### 4. `raise_exception`

> "If something's damaged or missing I open a ticket. Category, a few words about
> what happened, and which SKU it relates to."

### 5. `close_exception`

> "And close it when it's sorted, with a note about what we did."

## Notes from the Ops team

- "Don't make us type SKU codes if we can help it, we're wearing gloves."
- "It needs to tell us when it can't do something, in a way that makes sense.
  The old system just said `ERR_4001` and we had to ring IT."
- "Stock corrections feed the month-end count so they need to be right."
- "We had a problem last year where someone at Leeds could see Reading's numbers
  and quoted them to a customer. That shouldn't be possible."

## What Ops were not asked about, and did not consider

Nobody on the Ops side has thought about what happens when the assistant is
uncertain, or about which of these actions should be reversible. That is your
problem, not theirs. They will tell you they want everything to be fast.
