# Support Note: Scheduled advanced rules

## Initiative snapshot

- Initiative: Firewalla Local runtime buildout
- Focus: Capture the current understanding of persistent scheduled advanced rules, especially internet `disturb` and quota-backed internet rules
- Status: In progress
- Why this note exists: The active initiative plan now has enough live evidence that scheduled advanced rules need their own durable record instead of staying embedded in chat-only analysis

## Scope and non-goals

### In scope

- Persistent advanced-rule scheduling evidence from live inventory captures
- Current interpretation of `cronTime`, `duration`, and `autoDeleteWhenExpires`
- Candidate native signals that may indicate rule-window activity versus general rule traffic matches
- A bounded evidence backlog for future implementation work

### Non-goals

- Shipping a schedule-aware entity or attribute in this note alone
- Claiming the exact Firewalla recurrence contract is fully proven without wire captures or a wider matrix of schedule examples
- Generalizing `hitCount` or `lastHitTs` into a truthy "schedule active now" signal without more evidence

## Current live evidence summary

### Persistent scheduled internet disturb rule

The current strongest example is live rule `767`:

- `action`: `disturb`
- `target`: `TAG`
- `target_type`: `mac`
- `target_name`: `KADEN’s Devices (KADEN)`
- `matching.kind`: `internet_scope`
- `enabled`: `true`
- `expire_seconds`: `null`
- `is_temporary`: `false`
- `auto_delete_when_expires`: `true`
- `activated_time`: `null`
- `last_activated_time`: `1774464204.296`
- `cronTime`: `25 15 * * 1,3,5`
- `duration`: `46920`
- `disturbMethod.dropPacketRate`: `5`
- `disturbMethod.increaseLatency`: `10`

This strongly indicates a durable advanced-rule family with recurring schedule metadata rather than a simple temporary pause rule.

The user has now confirmed the intended meaning of this edited rule:

- start at `3:25 PM` on `Monday`, `Wednesday`, and `Friday`
- remain active for `13 hours, 2 minutes`
- end at `4:27 AM` the following day

That confirmation materially strengthens the working interpretation that `cronTime` and `duration` are the native recurring-window contract for this advanced-rule family.

Live rule `768` now confirms the same broader family can also appear as a category target-list disturb rule rather than only as an internet-scope rule:

- `action`: `disturb`
- `target`: `TLX-dt-netflix`
- `target_type`: `category`
- `matching.kind`: `category`
- `enabled`: `true`
- `expire_seconds`: `null`
- `is_temporary`: `false`
- `auto_delete_when_expires`: `true`
- `activated_time`: `null`
- `last_activated_time`: `null`
- `cronTime`: `0 17 * * 2,3`
- `duration`: `36000`
- `disturbMethod.dropPacketRate`: `10`
- `disturbMethod.increaseLatency`: `100`
- `notes`: `testing rules`

This adds three useful confirmations:

- persistent scheduled `disturb` is not limited to internet-scope `TAG` targets; it can also target category-backed target lists such as `TLX-dt-netflix`
- a persistent scheduled disturb rule can be fully enabled yet still show both `activated_time` and `last_activated_time` as `null`, which further weakens those fields as universal recurring-window indicators
- disturb-shaping parameters are carried directly on the durable rule payload and should be treated as first-class runtime metadata when this family is modeled later

The later sparse control-only pause experiment on the same rule adds the mutation result that matters most for implementation:

- `enabled` changed from `true` to `false`
- `updated_time` advanced to `1774471184.535`
- `idleTs` was added as `1774472984`
- `activated_time` remained `null`
- `last_activated_time` remained `null`
- `is_temporary` remained `false`
- `cronTime` remained `0 17 * * 2,3`
- `duration` remained `36000`
- `disturbMethod.dropPacketRate` remained `10`
- `disturbMethod.increaseLatency` remained `100`
- `notes` remained `testing rules`
- the rule ID stayed stable as `768`

Current conclusion from the sparse pause result:

- the control-only update path was sufficient for Firewalla to pause this durable scheduled disturb rule in place
- the rule was not obviously mangled by omitting the rest of the cached payload
- Firewalla preserved the full disturb schedule and shaping metadata while applying only pause-state fields
- this is materially stronger evidence than the temporary-rule test alone because it confirms sparse control-only mutation also works on a persistent advanced-rule family with recurring schedule metadata
- for this rule state, pausing did not create or expose any activation-history fields; the rule simply stayed disabled with `idleTs` populated, which is consistent with a durable rule that had not yet recorded an activation event

The matching sparse control-only resume experiment on the same rule adds the complementary durable-family result:

- `enabled` changed back from `false` to `true`
- `updated_time` advanced to `1774471265.763`
- `idleTs` cleared back to an empty string
- `activated_time` remained `null`
- `last_activated_time` remained `null`
- `is_temporary` remained `false`
- `cronTime` remained `0 17 * * 2,3`
- `duration` remained `36000`
- `disturbMethod.dropPacketRate` remained `10`
- `disturbMethod.increaseLatency` remained `100`
- `notes` remained `testing rules`
- the rule ID stayed stable as `768`

Current conclusion from the sparse resume result:

- the control-only update path was also sufficient for Firewalla to resume this durable scheduled disturb rule in place
- Firewalla restored the enabled control state without requiring replay of the cached full rule payload
- the rule kept the same recurring schedule, shaping metadata, notes, targeting surface, and durable classification across both sparse pause and sparse resume
- because both pause and resume succeeded cleanly on the same durable advanced-rule family, the evidence is now materially stronger that full cached-payload replay is unnecessary for at least this class of persistent rules
- taken together with the earlier temporary-rule results on `769`, this is the strongest current live evidence that sparse control-only mutation can preserve rule identity and semantics across both temporary and durable families

The later sparse pause experiment with an explicit `notes` override adds a second result that matters for payload-shape risk analysis:

- `enabled` changed from `true` to `false`
- `updated_time` advanced to `1774471807.868`
- `idleTs` was populated as `1774473607`
- `notes` changed from `testing rules` to `control-only overwrite test`
- `activated_time` remained `null`
- `last_activated_time` remained `null`
- `is_temporary` remained `false`
- `cronTime` remained `0 17 * * 2,3`
- `duration` remained `36000`
- `disturbMethod.dropPacketRate` remained `10`
- `disturbMethod.increaseLatency` remained `100`
- the rule ID stayed stable as `768`

Current conclusion from the sparse pause plus notes-override result:

- Firewalla did not ignore the extra mapped field; it accepted the sparse payload and overwrote the existing durable rule notes in place
- this proves the sparse update path is not limited to pause-state fields only; if the repository maps another mutable field correctly, Firewalla can apply that change without replaying the full cached rule body
- that is useful confirmation for field mapping, but it also sharpens the safety boundary: any additional field included on the sparse path is now part of the overwrite surface and must be treated deliberately
- the durable rule still preserved schedule and disturb-shaping metadata while applying both the pause state and the notes overwrite
- because `notes` changed while the rest of the durable rule stayed stable, this is strong evidence that Firewalla is performing an in-place partial update rather than requiring a full rule replacement contract

### Quota-backed internet rules

Live rules `764` and `765` now align with the same broad pattern:

- same internet-scope targeting surface as the disturb rule
- durable rule IDs rather than short-lived temporary-rule churn
- `cronTime` and `duration` present
- `appTimeUsage` and `appTimeUsed` present
- `autoDeleteWhenExpires` present even though the rules do not normalize as temporary rules

This supports the narrower interpretation already adopted in code: `autoDeleteWhenExpires` alone is not enough to classify a rule as temporary.

### Grouped app time-limit rule behavior

Live rule `763` adds an important third shape in this broader advanced-rule space:

- `action`: `app_block`
- `target`: `TLX-fw-facebook`
- `target_type`: `category`
- `enabled`: `true`
- `expire_seconds`: `null`
- `is_temporary`: `false`
- `auto_delete_when_expires`: `true`
- `dnsmasq_only`: `true`
- `cronTime`: `0 0 * * *`
- `duration`: `86390`
- `appTimeUsage.quota`: `60`
- `appTimeUsed`: `55`

The primary target name is misleadingly narrow. Although the canonical target key is `TLX-fw-facebook`, the actual grouped quota surface is broader:

- `targets`: `TLX-fw-facebook`, `TLX-fw-instagram`, `TLX-fw-tiktok`, `TLX-fw-youtube`
- `appTimeUsage.apps`: `facebook`, `instagram`, `tiktok`, `youtube`

Current conclusion:

- rule `763` is best interpreted as a persistent daily pooled app time-limit rule, not a Facebook-only block rule
- the quota bucket appears shared across at least Facebook, Instagram, TikTok, and YouTube
- `appTimeUsed: 55` against `quota: 60` strongly suggests about five minutes remained at capture time
- `cronTime: 0 0 * * *` plus `duration: 86390` is consistent with a daily reset at midnight and an all-day active accounting window
- `activated_time` and `last_activated_time` remaining `null` suggest the quota-enforcement transition had not yet been observed in this snapshot
- presentation logic will likely need model help later because `target_name` is absent and the first target key does not fully describe the grouped quota rule

The later quota-expired capture of the same rule adds the missing enforcement transition:

- `activated_time`: `1774467702.622`
- `last_activated_time`: `1774467702.622`
- `appTimeUsed`: `61`
- `appTimeUsage.quota`: `60`
- `hitCount`: `69`
- `lastHitTs`: `1774467774`
- `expire_seconds`: `null`
- `expires_at`: `null`
- `is_temporary`: `false`

Current conclusion from the quota-expired state:

- quota exhaustion appears to activate the durable grouped app-limit rule in place
- the rule does not convert into a temporary expiring rule when the allowance is exhausted
- `activated_time` and `last_activated_time` are now strong candidate signals for quota-enforcement activation on this rule family
- the rule remains installed after the app reports the allowance as expired; here, "expired" means the quota has been consumed, not that the rule object itself is expiring
- `appTimeUsed` can exceed the quota value, so the payload should be interpreted as accumulated accounting rather than a strict stop exactly at the threshold

The subsequent paused capture of the same rule adds the control-plane interpretation:

- `enabled`: `false`
- `activated_time`: `null`
- `last_activated_time`: `1774467702.622`
- `idleTs`: `1774470403.1893`
- `is_temporary`: `false`
- `appTimeUsed`: `61`

Current conclusion from the paused persistent state:

- the vendor appears to use the same pause or resume mechanism for persistent rules regardless of whether enforcement is currently active because of quota exhaustion or because the rule is simply installed and waiting for its next active condition
- on persistent rules, `enabled: false` plus populated `idleTs` is the strongest current signature for a paused rule
- pausing clears `activated_time` but preserves `last_activated_time`, which is consistent with "previously active, now paused" rather than deletion or conversion to a different rule type
- for persistent-rule control, the main user action is pause or resume, not create or delete temporary state

### Confirmed one-shot temporary disturb behavior

The same logical rule family was later observed in a true temporary state on rule `767`:

- `action`: `disturb`
- `target`: `TAG`
- `target_type`: `mac`
- `matching.kind`: `internet_scope`
- `enabled`: `true`
- `activated_time`: `1774464204.296`
- `last_activated_time`: `1774464204.296`
- `expire_seconds`: `2616`
- `expires_at`: `1774466820.296`
- raw `expire`: `2616`
- `auto_delete_when_expires`: `true`
- `is_temporary`: `true`

The user then confirmed the most important behavioral outcome: the rule was automatically deleted by Firewalla after the temporary run completed.

Current conclusion:

- `is_temporary: true` plus populated `expire_seconds` is the trustworthy signature for a one-shot temporary rule
- `autoDeleteWhenExpires` becomes meaningful once paired with real expiry fields
- the backend does auto-delete this temporary disturb rule family after expiry
- the exact meaning of the full `2616` second lifetime is still unresolved and should not be over-interpreted yet

### Confirmed one-shot temporary block behavior

Live rule `769` adds a cleaner non-disturb temporary example:

- `action`: `block`
- `target`: `social`
- `target_type`: `category`
- `target_name`: `social`
- `matching.kind`: `category`
- `enabled`: `true`
- `expire_seconds`: `3599`
- `expires_at`: `1774473938.188`
- `activated_time`: `1774470339.188`
- `last_activated_time`: `1774470339.188`
- `auto_delete_when_expires`: `true`
- `is_temporary`: `true`
- no `cronTime`
- no `duration`

This is useful because it removes several ambiguities that existed in the advanced-rule examples:

- true temporary rules do not need schedule metadata to normalize cleanly as temporary rules
- the combination of populated expiry fields, populated activation fields, and absent recurring schedule metadata is a much cleaner temporary signature than `autoDeleteWhenExpires` alone
- temporary category block rules can use the same durable-looking user-managed surface while still clearly representing a one-shot expiring rule object
- this strengthens the current repository rule: trust `is_temporary` plus expiry timing fields over `autoDeleteWhenExpires` when deciding whether a rule is durable enough for persistent switch semantics

The later sparse control-only pause experiment on the same rule adds an important mutation finding:

- `enabled` changed from `true` to `false`
- `updated_time` advanced to `1774470829.165`
- `activated_time` cleared back to `null`
- `last_activated_time` remained `1774470339.188`
- `idleTs` was added as `1774472629`
- `is_temporary` remained `true`
- `expire_seconds` remained `3599`
- raw `expire` remained present
- the rule ID stayed stable as `769`

Current conclusion from this sparse pause result:

- the control-only update path was sufficient for Firewalla to accept a timed pause on this temporary block rule
- the rule was not obviously mangled by omitting the rest of the cached payload
- Firewalla preserved the rule's temporary identity and expiry metadata while applying pause-state fields
- on this temporary-rule family, a pause appears to clear current activation state, preserve activation history, and add `idleTs` just as it does on persistent families
- this materially improves confidence that sparse control-only mutation may be a safer alternative to full cached-payload updates, though one successful family is not yet enough to generalize across all rule types

The subsequent sparse control-only resume experiment on the same rule adds the complementary result:

- `enabled` changed back from `false` to `true`
- `updated_time` advanced to `1774471069.997`
- `activated_time` repopulated as `1774471072.797`
- `last_activated_time` updated to `1774471072.797`
- `idleTs` cleared back to an empty string
- `is_temporary` remained `true`
- `expire_seconds` remained `3599`
- `expires_at` returned as `1774474671.797`
- the rule ID stayed stable as `769`

Current conclusion from the sparse resume result:

- the control-only update path was also sufficient for Firewalla to resume the same temporary rule in place
- Firewalla restored active temporary-rule timing state without requiring the rest of the cached rule payload
- the resume transition appears to re-anchor activation history on the new activation event, not preserve the earlier pre-pause activation timestamp
- `idleTs` clearing back to an empty string is consistent with the previously observed resume behavior on other rule families
- taken together, the pause and resume pair make rule `769` the strongest current evidence that sparse control-only mutations can preserve rule identity and semantics while avoiding cached-payload replay

## Interpretation of the current fields

### `cronTime`

Current best interpretation:

- recurring schedule start definition
- likely standard cron-style minute, hour, day-of-month, month, day-of-week shape
- day-of-week values appear to match the UI intent for multi-day recurring schedules

Current strongest example:

- historical example: `cronTime: 6 15 * * 1,3,4,5`
- latest confirmed example: `cronTime: 25 15 * * 1,3,5`
- user-confirmed UI intent for the latest example: start at 3:25 PM on Monday, Wednesday, and Friday

### `duration`

Current best interpretation:

- active window length in seconds after the scheduled start time
- the field follows rule edits and appears to move with the selected schedule window rather than with one-time pause semantics
- for the latest rule `767` capture, `46920` seconds equals 13 hours and 2 minutes, which matches the user-confirmed UI intent of starting at 3:25 PM and ending at 4:27 AM the next day

### `enabled`

Current best interpretation:

- on persistent rules, this is best interpreted as the vendor-managed pause or resume control state
- `enabled: true` means the persistent rule is not paused and can enforce whenever its native conditions are met
- `enabled: false` means the persistent rule has been paused
- it does not by itself mean the recurring schedule window is currently open
- for quota-backed app rules, it also does not by itself mean the quota has already been exhausted and enforcement is currently active
- rule `768` now provides a clean sparse pause and sparse resume pair for this same control-state interpretation on a scheduled disturb rule with recurring metadata intact
- the later `notes` overwrite experiment on the same rule shows that `enabled` can still be mutated cleanly alongside at least one non-control field without disturbing the recurring rule identity

### `idleTs`

Current best interpretation:

- on persistent rules, this is the strongest current native pause marker
- when populated together with `enabled: false`, it appears to indicate that the rule has been paused through the same vendor control path used elsewhere in the UI
- it should be interpreted separately from enforcement activation; a paused rule can preserve `last_activated_time` from an earlier active state while clearing `activated_time`
- rule `769` now shows the same field is also used on at least one true temporary block rule when that rule is paused in place
- the same rule also shows `idleTs` clearing back to an empty string on sparse resume, which strengthens confidence that this field is an actual control-state marker rather than incidental payload noise
- rule `768` now confirms the field is populated by sparse pause and cleared by sparse resume on a durable scheduled disturb rule whose schedule and shaping metadata remain unchanged
- the later `notes` overwrite experiment on rule `768` again populated `idleTs` while changing only one additional mapped field, which reinforces that the pause marker continues to behave independently from unrelated mutable metadata

### `notes`

Current best interpretation:

- this is a directly mutable user-visible field on at least the durable scheduled disturb family represented by rule `768`
- when included in a sparse `policy:update` payload, Firewalla applies the new value in place without requiring the rest of the cached rule body
- the field should therefore be treated as real overwrite surface, not incidental read-only metadata
- this experiment does not prove every rule family supports mutable notes, but it does prove the backend accepts the mapping on this durable advanced-rule family

### `autoDeleteWhenExpires`

Current best interpretation:

- not a reliable temporary-rule indicator by itself
- appears on both persistent scheduled advanced rules and truly temporary rules
- only becomes a strong temporary-rule signal when paired with actual temporary timing semantics such as normalized `expire_seconds`
- rule `768` reinforces the persistent side of that distinction, while rule `769` reinforces the temporary side

### `expire` and `expire_seconds`

Current best interpretation:

- these fields are the strongest native signals that a rule has entered a true temporary one-shot state
- when present together with `is_temporary: true`, they should be treated as authoritative temporary-rule markers
- the current evidence proves that this state auto-deletes, but does not yet fully explain whether the stored duration is user-facing duration, backend envelope duration, or time remaining from an earlier activation event
- rule `769` is the cleanest current example because it pairs expiry and activation fields without also carrying recurring schedule metadata
- after the sparse control-only pause, the same rule retained `expire_seconds` while losing computed `expires_at`, which suggests inventory may suppress or stop recomputing an active expiry boundary once the rule is paused even though the underlying temporary-rule contract remains intact
- after sparse control-only resume, `expires_at` returned with a fresh activation anchor, which supports the interpretation that computed expiry is tied to the current active run rather than being a fixed immutable property of the paused rule object

## Native signals that might indicate active schedule state

The repository should treat these signals differently by confidence level.

### Low confidence: `hitCount`

Why it is tempting:

- it increments when traffic matches the rule

Why it is not enough:

- it reflects observed traffic volume, not necessarily the rule-window state
- a busy child returning home can increase the counter even if the schedule hypothesis is still unresolved
- a quiet period could make an active rule look inactive if no traffic matches

Current conclusion:

- useful operational metadata
- not sufficient on its own for a truthful `is_schedule_active_now` attribute

### Low confidence: `lastHitTs`

Why it is tempting:

- it shows that matching traffic was seen recently

Why it is not enough:

- it is traffic-driven, not schedule-driven
- it can lag behind or stay quiet depending on user activity and network behavior

Current conclusion:

- useful operational metadata
- not sufficient on its own for a truthful schedule-state signal

For grouped app-limit rules such as `763`, these counters are better interpreted as post-activation enforcement traffic signals than as proof of when the underlying viewing session started.

### Medium confidence: `activatedTime`

Why it is tempting:

- the name suggests a transition into active state

Why it is not yet proven:

- for the latest rule `767` capture, normalized `activated_time` is still `null` even though the rule is enabled and has a valid recurring schedule
- that suggests the field may remain unset for installed scheduled advanced rules until some other event type occurs

Current conclusion:

- useful negative evidence when it stays `null`, but still not trustworthy as a direct current-window marker on its own
- when it is populated alongside `expire_seconds` and `is_temporary: true`, it is more useful as a temporary-rule activation anchor than as a recurring schedule-window indicator
- when it becomes populated on grouped app-limit rule `763` while the rule remains non-temporary, it is the best current native signal that quota enforcement has begun
- when that same persistent rule is later paused, `activated_time` clearing back to `null` appears to mark that enforcement is no longer active even though the durable rule still exists
- rule `768` strengthens the negative side of this interpretation because it is a configured recurring disturb rule with valid schedule metadata yet still carries `activated_time: null`
- rule `769` now shows the same clear-to-null behavior on a paused temporary rule, so `activated_time` should generally be treated as current enforcement-state metadata rather than as a durable identity field
- on sparse resume of rule `769`, `activated_time` repopulates with a new timestamp, which further supports treating it as the current active-run anchor rather than simply the original creation-time marker
- sparse pause of rule `768` leaves `activated_time` as `null`, which is consistent with the interpretation that pausing a not-currently-active recurring rule does not need to synthesize an activation-state transition

### Medium confidence: `lastActivatedTime`

Why it is tempting:

- the name suggests a more recent activation transition

Why it is not yet proven:

- for rule `767`, it remained populated while normalized `activated_time` stayed `null`
- the field may record the most recent activation event, but inventory alone still does not prove whether that event came from schedule entry, rule creation, or manual enablement

Current conclusion:

- the `activated_time is null` plus `last_activated_time is populated` combination is now the most promising native hint that a recurring rule is installed but not currently active, but confidence is still below implementation grade without more captures
- when both `activated_time` and `last_activated_time` are populated on a temporary rule, the pair appears consistent with a one-shot activation event, not with recurring-window presence
- when both fields populate together on non-temporary grouped app-limit rule `763`, they appear consistent with durable quota-enforcement activation rather than temporary expiry semantics
- when `last_activated_time` stays populated after a persistent rule is paused, it appears to preserve the most recent enforcement event rather than current control state
- rule `768` shows the fields can also both remain `null` on a valid enabled recurring disturb rule, so the repository should not treat missing activation history as proof that the schedule contract is invalid
- rule `769` shows that preserving `last_activated_time` across a sparse pause also holds on a temporary block rule, which strengthens the interpretation that this field is activation history rather than current control state
- on sparse resume of the same temporary rule, `last_activated_time` advances to match the new activation event, which is consistent with it tracking the most recent activation boundary regardless of whether the rule family is temporary or persistent
- sparse pause of rule `768` leaves `last_activated_time` as `null`, which is useful negative evidence that pausing alone does not create activation history on a recurring rule that has not yet shown a recorded activation event

### High confidence for pause semantics only: `idleTs`

Current conclusion:

- already proven useful for timed pause state on the currently implemented pause or resume service flow
- not present here as a live signal for the recurring advanced disturb schedule
- should not be assumed to help with recurring schedule windows

## Current rule `767` boundary interpretation

The most recent observation is:

- before the scheduled start and after the scheduled start, the rule object stayed structurally the same
- `hitCount` and `lastHitTs` increased
- `updatedTime`, `activatedTime`, and `lastActivatedTime` did not change

User clarification matters here:

- the increase in `hitCount` was caused by the child arriving home and generating traffic
- that means the traffic counters do explain observed activity, but they do not prove a schedule-state transition on their own

Current conclusion:

- recurring advanced rules appear to be runtime-evaluated against stable stored schedule metadata rather than rewritten at the schedule boundary
- inventory alone has not yet exposed a native field that can be trusted as a direct "currently in scheduled window" indicator

## Latest confirmed inactive-window interpretation for rule `767`

The latest edited version of rule `767` adds a more useful inactive-period data point:

- `cronTime: 25 15 * * 1,3,5`
- `duration: 46920`
- `activated_time: null`
- `last_activated_time: 1774464204.296`
- `updated_time: 1774466238.093`

At the time of inspection, the wall-clock was after the rule update but still before the next confirmed `3:25 PM` start for the active weekday under test. The user also confirmed that this was intentional and that the rule should not currently be disturbing.

Current conclusion from this snapshot:

- `enabled: true` means the recurring disturb rule is installed
- `activated_time: null` is consistent with the rule not currently being in its active disturb window
- populated `last_activated_time` likely records a prior activation event rather than the current one
- the pair `activated_time: null` and `last_activated_time: <timestamp>` is currently the best native payload clue for "scheduled rule exists, but is not active right now"
- this remains a hypothesis until confirmed by a matching active-window capture of the same rule shape

## Latest confirmed temporary-rule interpretation for rule `767`

The subsequent capture of rule `767` showed the same disturb family in a true expiring state:

- `is_temporary: true`
- `expire_seconds: 2616`
- `expires_at: 1774466820.296`
- raw `expire: 2616`
- `activated_time: 1774464204.296`
- `auto_delete_when_expires: true`

The important confirmed outcome is behavioral, not mathematical: the rule later disappeared automatically from inventory.

Current conclusion from this snapshot:

- Firewalla can represent advanced `disturb` rules in at least two distinct modes: durable recurring scheduled rules and true temporary expiring rules
- the temporary mode is clearly identifiable from `is_temporary`, `expire_seconds`, and `expires_at`
- auto-deletion after expiry is now confirmed behavior, not just inference
- the exact relationship between the observed user-facing one-minute test window and the stored `2616` second expiry value remains unresolved
- until that mismatch is explained, the repository should trust temporary classification fields more than inferred duration semantics

## Implementation implications

### Safe today

- expose `cronTime` and `duration` as schedule metadata
- expose `hitCount` and `lastHitTs` as operational metadata if desired
- expose disturb-shaping fields such as latency and packet-drop controls for disturb-family rules once that family is implemented
- treat `activated_time` and `last_activated_time` on grouped app-limit rules as promising enforcement-state metadata
- treat `enabled` on persistent rules as the best current pause or resume control state
- expose `idleTs` on persistent rules as pause-state metadata

### Not yet safe to claim

- a direct `schedule_active_now` attribute based solely on native payload fields
- a direct `activated_by_schedule` attribute based on `activatedTime` or `lastActivatedTime`
- a fully explained user-facing meaning for `expire_seconds` on one-shot disturb rules beyond "this rule is temporary and will auto-delete"
- that grouped app-limit activation fields reset only at midnight rather than on pause, resume, or other quota-related transitions
- that every persistent rule family uses `idleTs` identically until more than one persistent family is observed being paused and resumed through the vendor UI

### Most honest near-term approach

- use switch semantics for persistent-rule pause or resume control rather than for current enforcement activity
- expose enforcement activity through attributes such as `activated_time`, `last_activated_time`, quota usage, and schedule metadata
- if the integration needs a current schedule-state attribute, derive it locally from `cronTime`, `duration`, and the box timezone
- continue recording the native `activated_time` and `last_activated_time` pairing so we can later decide whether it is useful as corroborating evidence
- treat `is_temporary`, `expire_seconds`, and `expires_at` as the authoritative boundary for excluding one-shot rules from durable switch eligibility
- keep any derived schedule-state attribute clearly identified as integration-derived rather than native Firewalla payload state

## Evidence backlog

1. Capture a rule snapshot for the same scheduled advanced rule during a known inactive period with no matching traffic and compare `hitCount`, `lastHitTs`, and stable timing fields.
2. Capture the exact local mutation payload for creating or updating a persistent advanced `disturb` rule.
3. Verify whether other advanced scheduled rule families use the same `cronTime` plus `duration` contract.
4. Confirm whether any payload field changes exactly at schedule end, not just schedule start.
5. Record the box timezone alongside future schedule captures so derived schedule-state calculations stay truthful.
6. Capture the same recurring `disturb` rule during a known active window and compare whether `activated_time` becomes populated while `last_activated_time` advances.
7. Capture another one-shot `disturb` rule from creation through deletion so the meaning of the stored `expire_seconds` value can be compared against the user-facing configured duration.
8. Capture post-quota snapshots for rule `763` to see whether quota exhaustion mutates the existing durable rule in place or causes a temporary enforcement state.
9. Capture a paused and resumed persistent rule from at least one additional family, such as scheduled disturb or internet block quota, to confirm that `enabled` and `idleTs` are truly shared control signals across persistent rule types.

## References

- `plans/completed/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_COMPLETE.md`
- `custom_components/firewalla_local/models.py`
- `custom_components/firewalla_local/switch.py`
- `custom_components/firewalla_local/helpers/runtime_inventory.py`
- `.tmp/20260425_inventory.txt`
