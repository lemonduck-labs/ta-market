# 0001: No council names in anything shared

Date: 21 October 2026. Status: decided by the owner.

## Decision

Nothing shared outside the repo names a council in a comparison: not the report, not the
demo, not a pitch. The shareable demo shows one example council against unnamed peers
("yours against others"). For a pitch to a particular council, a private copy may name
that council on its own figures only; its peers stay unnamed.

Working copies that name councils in comparison lists stay in `reports/private/` and
`data/private/`, which git ignores.

## Why

A list of named councils far from their peers reads as a judgement, even when the text
says it is a lead and most of the gaps come from how spend is recorded. Naming adds nothing
the comparison needs: a council officer wants to see where their own council sits.

## Consequences

- The tracked council tables keep each council's own published figures, as MHCLG publishes
  them; the flags that select councils as leads or recording checks stay private.
- The demo's council picker offers anonymised example councils, never a list of names.

## Revisit

Owner, 21 October 2026: no names yet. When a private version is shared with a council
(for example behind a private key), naming that council on its own figures can be
switched on for that copy. Log the change here when it happens.
