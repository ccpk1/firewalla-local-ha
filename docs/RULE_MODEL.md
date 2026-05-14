# Firewalla Local rule model

## Purpose

This document defines the durable rule-model contract used by the Firewalla
Local integration.

It records how normalized Firewalla policy rules should be interpreted for:

- control semantics
- switch eligibility
- metadata exposure
- presentation fallbacks

This document is the long-term model reference. It is not a capture log.
Evidence and packet-level workflow remain in
`docs/REVERSE_ENGINEERING_WORKFLOW.md`.

## Modeling approach

Rule modeling should start from the narrowest trustworthy Firewalla contract,
not from whichever local fields happen to appear first in captures.

When Firewalla publishes a rule action, write payload, read payload, or data
model, treat that material as the first-choice contract for outward-facing
normalization.

This means the rule model should be built in three layers:

- raw local payload: the exact fields observed from the local box transport
- canonical Firewalla rule: the normalized rule shape that stays as close as
  practical to Firewalla's published nouns and structure
- Home Assistant rule view: derived convenience fields used for selection,
  readability, service UX, and entity behavior

Critical rules:

- do not collapse these layers into one convenience model
- do not let a single local capture redefine a published Firewalla concept
- do not expose Home Assistant-derived convenience fields as if they were
  Firewalla-native fields

### Contract precedence

Use the following precedence order when deciding how a rule field or action
should be modeled.

1. published Firewalla action contract
2. published Firewalla write contract
3. published Firewalla read contract or data model
4. confirmed local runtime payloads and mutation captures
5. Home Assistant-specific derived fields

Interpretation rules:

- action surfaces should stay as narrow as the published contract allows
- create and update surfaces should prefer published first-class inputs over
  inferred convenience blobs
- read models should prefer published object families and nesting before adding
  integration-specific flattening
- local-only fields may be normalized when they are useful, but they must be
  marked as integration extensions rather than treated as canonical Firewalla
  fields

### Extension policy

The integration may add derived rule fields when they improve Home Assistant
behavior or readability, but those additions must stay explicit.

Examples of acceptable derived fields:

- `is_paused`
- `pause_until`
- `schedule_window`
- `current_state_reason`
- switch-eligibility and review metadata

Rules for derived fields:

- derive them from canonical fields whenever possible
- name them as interpretations, not raw Firewalla facts
- keep them out of mutation payload contracts unless Firewalla publishes the
  same concept directly

Identity interpretation rule:

- when local rule payloads identify applicability through a backing group or tag that has affiliated user metadata, the Home Assistant-facing readable name should prefer the affiliated user identity over the backing group name
- raw backing group names remain valid inventory or diagnostic evidence, but they are not the default presentation contract for rule names or related metadata

### Practical design consequence

For future rule services, the working default should be:

- start from the published Firewalla contract
- map local runtime or mutation data into that contract
- add explicit integration extensions only where Home Assistant needs them

This approach keeps the integration aligned with Firewalla's public direction
while still allowing local-only runtime evidence to fill gaps.

## Core model

The integration now treats Firewalla policy rules through two separate lenses:

- control semantics: how the rule behaves when paused, resumed, enabled,
  disabled, created, or deleted
- metadata surface: the extra fields that describe schedule, quota, traffic
  shaping, app identity, targeting, or port-forward context

Critical rule:

- do not split rule families by target type alone when the actual control
  behavior is shared

## Persistent rule control model

Current confirmed rule families show the same persistent control behavior when
they are user-managed and not temporary.

Confirmed control invariants:

- pause is an in-place state change, not a logical delete
- pause sets `enabled = false`
- pause clears `activated_time`
- pause preserves `last_activated_time`
- pause advances `updated_time`
- pause populates raw `idleTs`
- resume is an in-place state change on the same rule object
- resume sets `enabled = true`
- resume clears raw `idleTs`
- resume repopulates `activated_time`
- resume advances `last_activated_time`
- resume advances `updated_time`
- family-specific metadata survives pause and resume unless explicitly mutated

These invariants are currently confirmed across the following durable families:

- `allow`
- `block`
- `disturb`
- `qos`
- port-forwarding-flavored `allow`

## Temporary rule model

Temporary rules are a separate control family.

Current interpretation rules:

- `autoDeleteWhenExpires` alone is not enough to classify a rule as temporary
- the strongest current temporary signature is normalized `is_temporary = true`
  together with populated expiry metadata
- reliable temporary indicators include:
  - `expire_seconds`
  - `expires_at`
  - raw `expire`
- temporary rules may disappear automatically after expiry instead of remaining
  installed in a disabled or paused state

## Switch eligibility model

Switch eligibility should be driven by control semantics first and presentation
quality second.

### Control-first policy

A rule is a switch candidate only when all of the following are true:

- the rule is user-managed
- the rule is persistent
- the rule is not temporary
- the rule action belongs to the supported controllable action set
- the rule purpose belongs to the approved switch-purpose set

### Supported controllable actions

The currently confirmed controllable action set is:

- `allow`
- `block`
- `disturb`
- `qos`

Notes:

- app-selected rules may still appear as ordinary `block` rules with
  category-backed targets such as `TLX-fw-roblox`
- historical `app_block` observations should be treated as a specialized app
  enforcement shape rather than the baseline app-rule contract unless that
  action reappears in fresh captures

### Default excluded purposes

These purpose values should remain excluded from the switch surface:

- `family`
- `dap`
- `firewall`

Notes:

- `dap` refers to Device Active Protect and should be treated as a
  product-owned protection surface, not a normal user switch surface
- port-forwarding rules are now confirmed to use the same durable pause or
  resume contract and should be treated as an approved switch purpose

Important distinction:

- inclusion of `port_forwarding` is supported by live pause or resume evidence;
  the control mechanics match the shared durable rule model

### Approved switch purposes

The currently approved switch purposes are:

- `null`
- `port_forwarding`

### Review reasons are not control blockers

Review reasons are presentation and confidence hints only.

They must not, by themselves, change a rule from controllable to
non-controllable.

Examples:

- `missing_readable_target_name`
- `missing_tag_target_resolution`
- `target_list_reference`
- `missing_target_list_name`

Those reasons affect naming quality, not the underlying rule-control model.

## Metadata groups

The integration should expose metadata in optional groups instead of treating
each metadata shape as a separate control family.

### Common control metadata

These fields are relevant across most persistent rules:

- `enabled`
- `activated_time`
- `updated_time`
- `last_activated_time`
- raw `idleTs`
- `notes`
- raw `_name`

Interpretation rule:

- raw `_name` is a user-defined display name and should be preferred for
  options-list and other user-facing rule naming when present
- raw `app_name` should be preferred over internal category target slugs such as `TLX-fw-*` when both are present and the surface is user-facing

### Identity and naming metadata

The integration may need to derive readable rule applicability and target names
from multiple raw fields.

Interpretation rules:

- affiliated user identity is the first-choice readable name for user-scoped applicability when Firewalla models that scope through a backing group
- backing group names are evidence of the underlying payload shape, not the default user-facing label
- app-backed category rules should prefer `app_name` over raw `TLX-*` target slugs on user-facing surfaces

### Timing and expiry metadata

These fields describe temporary behavior or durable timing context:

- `expire_seconds`
- `expires_at`
- `auto_delete_when_expires`
- raw `expire`

Interpretation rules:

- expiry fields indicate temporary countdown semantics when paired with
  `is_temporary`
- `auto_delete_when_expires` on its own may still appear on durable rules and
  must not be treated as sufficient evidence of temporary behavior

### Schedule metadata

These fields describe recurring active windows on durable advanced rules:

- raw `cronTime`
- raw `duration`

Current interpretation:

- `cronTime` and `duration` describe the recurring schedule window
- these fields are schedule metadata, not a separate control model

### Quota metadata

These fields describe app-time or internet-time accounting:

- raw `appTimeUsage`
- raw `appTimeUsed`

Current interpretation:

- these are durable quota and accounting fields
- they do not by themselves mean a rule is temporary
- quota exhaustion can activate a durable rule in place instead of creating a
  separate temporary rule object

### App-backed metadata

These fields identify app-backed category rules:

- raw `app_name`
- raw `app_uid`
- targets like `TLX-fw-*`

Current interpretation:

- app-selected rules may normalize as category-backed `allow` or `block` rules
- app identity is metadata layered on top of shared control semantics

### Disturb metadata

These fields describe traffic shaping for disturb rules:

- raw `disturbLevel`
- raw `disturbMethod`
- `disturbMethod.dropPacketRate`
- `disturbMethod.increaseLatency`

Current interpretation:

- these are first-class descriptive fields for disturb rules
- they do not imply a different pause or resume model

### QoS metadata

These fields describe QoS behavior:

- raw `trafficDirection`
- raw `priority`
- raw `qdisc`
- raw `rateLimit`
- raw `app_name`
- raw `app_uid`

Current interpretation:

- QoS follows the same persistent control model as the other durable families
- QoS-specific fields should be exposed as optional metadata, not used as a
  reason to split the rule into a different control system

### Port-forward metadata

These fields describe port-forward target-list rules:

- raw `localPort`
- raw `protocol`
- raw `guids`
- raw `userTargetList`

Current interpretation:

- these rules are controllable through the same persistent pause or resume
  pattern
- they remain outside the default switch surface unless the product scope is
  widened intentionally

## Targeting and readability model

Target readability and target resolution quality are separate from control
eligibility.

Key targeting fields:

- `target`
- `target_name`
- `target_type`
- `scope`
- `applies_to`
- `tag_refs`

Interpretation rules:

- missing `target_name` does not mean the rule is unsupported
- missing tag or target-list resolution does not mean the rule cannot be
  paused or resumed safely
- presentation should prefer readable resolved names when available
- fallback labeling may use `scope`, `applies_to`, or stable internal target
  identifiers when a readable name is absent

## Proven family summary

| Shape | Example interpretation | Control model | Metadata emphasis |
| --- | --- | --- | --- |
| direct `allow` | DNS, IP, network, target-list allow | persistent in-place pause or resume | targeting, notes |
| direct `block` | category, internet, app-backed category block | persistent in-place pause or resume | targeting, app, schedule, quota |
| `disturb` | scheduled or scoped traffic shaping | persistent in-place pause or resume | disturb, schedule |
| `qos` | internet or category QoS | persistent in-place pause or resume | QoS, app |
| temporary block | short-duration quick block | temporary create plus expiry or delete | expiry |
| port forwarding | inbound allow using target lists | persistent in-place pause or resume | port-forward context |

## Documentation rule

When the model changes:

- update this document for durable interpretation changes
- update `docs/ARCHITECTURE.md` for architectural contract changes
- update `docs/REVERSE_ENGINEERING_WORKFLOW.md` for new evidence, captures, and
  confirmed invariants