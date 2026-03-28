# Initiative Plan: Firewalla Local data access research

## Initiative snapshot

- Initiative: Firewalla Local data access research
- Status: In process
- Owner: Firewalla Strategist
- Primary outcome: Determine whether the Firewalla mobile app or local box exposes narrower or more real-time local data paths than the current full runtime-init snapshot pull.
- Why now: `1.0.0` is released, and the next meaningful performance question is whether refresh efficiency can improve through a better local data access strategy rather than by incremental tuning alone.

## Scope and non-goals

### In scope

- Document the current local refresh path and its practical payload characteristics.
- Compare the local integration approach against MSP-based community integrations only to identify feature ideas and protocol differences.
- Define a focused packet-capture and app-behavior research workflow centered on the local mobile app experience.
- Record findings that distinguish full-snapshot refresh behavior from any narrower pull or real-time telemetry path.
- End with a clear recommendation on whether to pursue transport discovery, protocol extension, or downstream optimization.

### Non-goals

- Do not change production integration code during this initiative.
- Do not assume undocumented Firewalla local endpoints are real until capture evidence confirms them.
- Do not treat MSP API behavior as proof of local box behavior.
- Do not commit to a future implementation plan until the research results justify one.

## Open questions or external dependencies

1. Does the mobile app use the same encrypted local Encipher request path for overview refreshes that the integration already uses?
2. Is the throughput graph powered by a separate streaming channel, repeated lightweight polling, or a narrower encrypted request shape?
3. When the app user presses refresh, is the refresh global, page-specific, or a hybrid of baseline plus page-scope calls?
4. What capture environment is available for the mobile app workflow: packet sniffing on the LAN, proxy tooling, device-side instrumentation, or box-side tcpdump?

Confirmed research access for this initiative:

- direct local runtime pulls are working from this dev environment via `utils/pull_runtime.py` using the active Home Assistant config entry
- SSH access to the Firewalla box is working via the documented reverse-engineering path using `.tmp/firewalla_temp_ssh_key` and `pi@fire.walla`
- `docs/REVERSE_ENGINEERING_WORKFLOW.md` is the active operational reference for Firewalla-side packet capture, artifact handling, and decryption workflow reuse

## Phase summary table

| Phase | Focus | Deliverable | Notes |
| --- | --- | --- | --- |
| 1 | Current-state baseline | Verified summary of current refresh mechanics | Uses repo analysis and live read-only probing only |
| 2 | Capture design | Simple worksheet for overview and refresh traffic capture | Starts on the main overview page |
| 3 | Evidence collection and comparison | Findings on full pull vs page-specific vs real-time paths | Depends on packet capture and app access |
| 4 | Recommendation and next-step decision | Research conclusion with ranked follow-up options | May produce a later implementation plan if justified |

## Per-phase details with checkboxes

### Phase 1: Current-state baseline

Goal: Confirm how the integration pulls data today and identify what has already been disproven.

- [x] Confirm the active integration refresh path in `custom_components/firewalla_local/coordinator.py` and `custom_components/firewalla_local/api/client.py`.
- [x] Verify that the current local protocol uses the encrypted Encipher message endpoint on port `8833` rather than plain local REST polling.
- [x] Capture one or more live runtime artifacts using `utils/pull_runtime.py` to measure payload size and top-level structure.
- [x] Compare sequential runtime pulls to identify which top-level sections actually churn between refreshes.
- [x] Probe candidate narrower `init/get` requests and document whether they return a reduced payload or the same full snapshot shape.
- [x] Probe candidate plain HTTP and WebSocket paths on port `8833` and record whether they expose an obvious alternative surface.
- [x] Review MSP-based community integrations for useful endpoint ideas while keeping the local-vs-cloud distinction explicit.

Phase 1 execution note: completed.

- The integration currently performs one encrypted local runtime-init pull per update cycle.
- Live runtime payload size is about `1.28 MB` per pull.
- Sequential pull comparison showed a limited set of top-level sections changing, but transport volume remains dominated by the full snapshot.
- Candidate granular `init/get` probes returned the same full payload shape rather than a narrower slice.
- Candidate plain local REST and WebSocket paths returned `400`, so there is no current evidence of a directly discoverable unauthenticated or obvious side-channel surface.
- MSP community integrations remain useful for feature inventory, but not as proof of local transport behavior.

### Phase 2: Capture design

Goal: Define a small, repeatable capture workflow that can answer the remaining transport questions without broad exploratory drift.

- [x] Write a capture worksheet centered on the Firewalla mobile app overview page.
- [x] Define a steady-state overview capture where the app is opened and left idle for `30-60` seconds.
- [x] Define a manual-refresh capture from the overview page.
- [x] Define one page-transition capture from overview to a single feature page such as alarms, networks, or VPN.
- [x] Define one known-change capture where the app is refreshed after a deliberate state change.
- [x] Record exactly which packet characteristics to compare across captures: request timing, burst size, response size, connection reuse, and any upgrade or stream behavior.

Phase 2 execution note: completed.

- The capture workflow is intentionally overview-first because the overview page is the most likely place to expose both the baseline snapshot behavior and any separate throughput telemetry path.
- The default comparison page for the first page-transition capture is alarms because it is a plausible candidate for page-specific refresh behavior while remaining distinct from throughput.
- The worksheet stays evidence-driven and transport-agnostic: it records observable packet characteristics first and avoids assuming REST, WebSocket, or custom protocol shapes in advance.

Capture worksheet:

1. Session A: overview idle
  - Start packet capture before opening the Firewalla app.
  - Open directly to the main overview page.
  - Do not tap anything for `30-60` seconds.
  - Record whether traffic settles into:
    - one initial burst only
    - repeated small requests or responses
    - one long-lived connection
  - Primary question: does live throughput rely on a distinct steady-state path?

2. Session B: overview manual refresh
  - Begin from the overview page in a stable idle state.
  - Trigger one manual refresh only.
  - Record the request burst immediately before and after the refresh gesture.
  - Compare against Session A to identify whether refresh adds:
    - one large request or response pair
    - several smaller requests
    - no change to any long-lived connection
  - Primary question: is overview refresh a full snapshot pull or a lighter refresh path?

3. Session C: overview to alarms
  - Start from the overview page after the initial load is complete.
  - Navigate to the alarms page and wait `10-15` seconds.
  - Trigger one manual refresh on the alarms page if the app provides it.
  - Record whether navigation or refresh introduces a new traffic pattern distinct from overview.
  - Primary question: are secondary pages using page-specific refresh behavior or reusing the same shared snapshot path?

4. Session D: known-change then refresh
  - Create one deliberate state change on the Firewalla box that should be observable in the app.
  - Recommended examples:
    - pause or resume a rule
    - create or dismiss one alarm if safely possible
    - change a network or VPN state only if the action is low risk
  - From the overview page, trigger one refresh and record the traffic burst.
  - Then navigate to the most relevant page for that change and refresh again.
  - Primary question: is refresh global, page-specific, or baseline plus page-scope follow-up?

Packet characteristics to record for every session:

- timestamp of each burst start and stop
- destination host and port
- HTTP method and path if visible
- whether the connection upgrades or remains plain HTTP
- request count per burst
- approximate response size per burst
- whether the same connection is reused across actions
- whether steady-state traffic continues after the page becomes visually stable

Interpretation guide:

- One large encrypted burst on load and on every refresh supports the current full-snapshot model.
- A large initial burst plus smaller follow-up bursts supports a hybrid model with page-specific or telemetry-specific reads.
- A long-lived connection or repeated low-volume messages only while overview throughput is visible supports a separate telemetry path for throughput.
- Distinct request bursts when opening alarms but not during overview idle supports page-specific refresh behavior.
- Identical burst patterns across overview and alarms refreshes supports one shared snapshot path reused by multiple pages.

### Phase 3: Evidence collection and comparison

Goal: Use targeted captures to determine whether the app uses a separate throughput channel or page-specific refresh behavior.

Phase 3 execution prerequisites confirmed:

- Firewalla-side SSH capture access is available
- direct live payload pull access is available
- the repository already contains reusable workflow and helper references in `docs/REVERSE_ENGINEERING_WORKFLOW.md`, `.tmp/capture_runtime_inventory.py`, `utils/pull_runtime.py`, and `utils/analyze_capture.py`

- [x] Capture overview-page traffic and isolate any repeated small telemetry flow associated with live throughput.
- [x] Capture manual refresh from the overview page and compare it against the current integration runtime-init behavior.
- [x] Capture navigation from overview to one secondary page and determine whether the app issues new page-specific calls.
- [x] Compare encrypted request burst patterns to determine whether the app is reusing full pulls or issuing smaller follow-up calls.
- [x] Record whether throughput appears to come from a stream, repeated small pulls, or the same full refresh mechanism.
- [x] Summarize the evidence as one of three outcomes: full snapshot only, snapshot plus narrow follow-up calls, or separate real-time telemetry channel.

Phase 3 progress note: Session A overview idle capture completed.

Session A findings so far:

- The overview idle capture produced a valid Firewalla-side pcap at `.tmp/firewalla_overview_idle_capture.pcap` and a decoded preview at `.tmp/firewalla_overview_idle_capture.decoded.txt`.
- One app-originated request was positively decoded as a local `init` message to `/v1/encipher/message/{gid}` with `target=0.0.0.0`.
- That decoded request included additional request data keys not used by the current integration baseline, including `dapOps` and `fwapcOps`, which suggests the mobile app may request more than the repository's current minimal init payload shape during overview load.
- The capture also showed additional app-side exchanges on port `8833` that the current decoder did not fully decrypt cleanly.
- One localhost exchange hit `/v1/encipher_raw/message/{gid}`, which is notable because the current integration does not use the `encipher_raw` path.
- The overview-idle traffic pattern therefore does not yet prove a separate throughput stream, but it does prove that the app-side overview path is not limited to a single trivially identical request shape.

Current interpretation after Session A:

- there is confirmed overlap with the existing full init-style pull
- there is also evidence of additional local protocol behavior that the current helper does not fully decode yet
- throughput may still rely on repeated smaller requests or an alternate encrypted path, but Session A alone is not enough to classify it as a dedicated stream

Immediate implication for the next capture:

- Session B should compare overview manual refresh against this idle baseline to determine whether refresh introduces another full init burst, reuses the same auxiliary traffic, or triggers a distinct request family

Phase 3 progress note: Session B overview manual refresh capture completed.

Session B findings so far:

- The manual-refresh capture produced a valid Firewalla-side pcap at `.tmp/firewalla_overview_refresh_capture.pcap` and a decoded preview at `.tmp/firewalla_overview_refresh_capture.decoded.txt`.
- Session B again showed a decoded app-originated `init` request to `/v1/encipher/message/{gid}` with `target=0.0.0.0` and the same additional request data keys seen in Session A, including `dapOps` and `fwapcOps`.
- Session B also repeated the localhost `/v1/encipher_raw/message/{gid}` activity seen in Session A.
- Compared with Session A, Session B had fewer distinct 8833 flows but still showed multiple response-heavy exchanges beyond the one decoded `init` request.
- The dominant response payload volume in Session B remained centered on one large response flow of roughly the same size class as the full init-style response seen during idle overview loading.

Current interpretation after Session B:

- overview manual refresh clearly reuses the same decodable `init` request family already observed during overview idle loading
- there is still auxiliary 8833 traffic around that refresh cycle that the current decoder does not fully interpret
- the current evidence therefore favors a model where overview refresh includes at least one full init-style pull rather than a clearly separate lightweight refresh path
- the remaining uncertainty is whether the auxiliary traffic represents page-local follow-up reads, throughput-related telemetry, or helper requests the app issues around both load and refresh

Immediate implication for the next capture:

- Session C should move from overview to alarms to determine whether a secondary page introduces a distinct request family or simply rides on the same overview-style init plus auxiliary traffic pattern

Phase 3 progress note: Session C overview-to-alarms capture completed.

Session C findings so far:

- The alarms-session capture produced a valid Firewalla-side pcap at `.tmp/firewalla_overview_to_alarms_capture.pcap` and a decoded preview at `.tmp/firewalla_overview_to_alarms_capture.decoded.txt`.
- Session C again included the same decodable app-originated `init` request to `/v1/encipher/message/{gid}` with `target=0.0.0.0` and the same observed request data keys, including `dapOps` and `fwapcOps`.
- Session C again included localhost `/v1/encipher_raw/message/{gid}` activity.
- Compared with Session B, Session C produced a larger overall capture and a larger total 8833 payload volume.
- Session C also showed two additional response-heavy flow pairs beyond the single dominant init-style response flow, which suggests the alarms-page navigation or alarms-page refresh introduced extra local exchanges not visible in the simpler overview-refresh capture.

Current interpretation after Session C:

- the same full init-style request family still appears to be part of the secondary-page path
- the alarms session is heavier than overview manual refresh, which supports the idea that page navigation or page refresh can introduce additional local reads around the shared init baseline
- the current decoder still does not fully interpret those additional exchanges, so the page-specific behavior is evidence-based but not yet fully classified by message type

Immediate implication for the next capture:

- Session D should use one deliberate state change and then compare overview refresh with a relevant page refresh to determine whether those extra exchanges are tied to page scope, changed data scope, or both

Phase 3 progress note: Session D archived-alarm capture completed.

Session D findings so far:

- The known-change capture produced a valid Firewalla-side pcap at `.tmp/firewalla_session_d_alarm_change_capture.pcap` and a decoded preview at `.tmp/firewalla_session_d_alarm_change_capture.decoded.txt`.
- Session D included one clearly decoded command before the follow-up refresh traffic:
  - `mtype=cmd`
  - `data={"item": "alarm:ignore", "value": {"alarmID": "18579"}}`
- After that archive command, the app issued two separate `mtype=init` requests to `/v1/encipher/message/{gid}` with `target=0.0.0.0` and the same observed `dapOps` and `fwapcOps` payload shape seen in Sessions A through C.
- Session D again included localhost `/v1/encipher_raw/message/{gid}` activity.
- The post-change direct runtime pull confirmed that the archived alarm changed box state in the expected direction:
  - `activeAlarmCount` moved from `575` to `574`
  - `archivedAlarmCount` moved from `126` to `127`
  - `newAlarms` remained at `50`
- Session D was the heaviest capture of the four completed sessions at about `1.64 MB` of port-`8833` TCP payload, driven by two dominant response flows of roughly `544 KB` each plus additional response-heavy flows around the mutation and page activity.

Current interpretation after Session D:

- the app does use narrower encrypted commands for at least some page-scoped actions, because the alarm archive action was captured directly as a discrete `mtype=cmd` request rather than being folded into an opaque full refresh
- once that mutation completes, the app still appears to refresh by issuing full init-style pulls, and Session D showed that behavior twice in one user flow
- the current evidence therefore rules out a "lightweight refresh only" model for the observed alarms workflow and instead supports a hybrid model: discrete narrow commands or page-related calls layered around the same large init baseline
- across Sessions A through D, there is still no evidence of a long-lived upgraded connection or clearly persistent low-volume steady-state stream dedicated to overview throughput telemetry

Phase 3 conclusion:

- Best-fit outcome: `snapshot plus narrow follow-up calls`
- What is now proven:
  - the mobile app reuses the same full init-style request family observed in the current integration baseline
  - secondary page workflows can add extra local exchanges beyond that shared init baseline
  - at least one page action, alarm archive, is implemented as a distinct narrow encrypted command on the same local Encipher transport
- What remains unproven:
  - the exact message types of the extra non-init exchanges seen around secondary-page use
  - whether overview throughput uses an additional narrow read command that did not surface distinctly in the current four sessions
  - whether any of the undecoded `encipher_raw` localhost activity materially contributes to user-visible data refresh behavior

Throughput interpretation after Phase 3:

- The current captures do not support a separate real-time telemetry channel.
- No WebSocket upgrade, long-lived streaming connection, or recurring low-volume overview-idle traffic pattern was observed on port `8833`.
- The evidence currently favors overview data being refreshed through the same init-style snapshot mechanism, potentially with auxiliary follow-up calls that still need deeper decoding.

Phase 3 capture hygiene rules:

- Firewalla `/tmp` is temporary staging only, not durable artifact storage.
- The workspace `.tmp/` directory is the working artifact location for pcaps, decoded outputs, and comparison files during this initiative.
- Before every new remote capture:
  - check available space under remote `/tmp`
  - remove only stale Firewalla capture files that have already been copied locally and are no longer needed on the box
- After every capture:
  - stop `tcpdump` cleanly with `SIGINT`
  - verify the remote pcap exists and has a non-zero size
  - copy the pcap into local `.tmp/` immediately
  - verify the local copy exists before deleting the remote pcap
  - delete the remote pcap after a successful local copy unless there is a specific reason to keep it temporarily
- If remote `/tmp` free space drops to a level that risks failed captures, pause capture work and clean remote staging files before continuing.

Operational handling plan for remaining sessions:

- keep one active remote pcap at a time
- keep durable working copies locally under `.tmp/`
- record remote file size and local file presence for each capture session
- prefer frequent transfer-and-delete cycles over accumulating multiple captures on the Firewalla box

### Phase 4: Recommendation and next-step decision

Goal: End the research with a grounded recommendation rather than an open-ended reverse-engineering backlog.

Phase 4 execution note: completed.

- [x] Decide whether the most promising next step is transport discovery, narrower encrypted command discovery, or downstream optimization of parsing and reconciliation.
- [x] Rank the likely high-value follow-up areas such as throughput telemetry, alarms, VPN status, and network status.
- [x] Record what is proven, what is still inferred, and what would require a deeper protocol effort.
- [x] Decide whether a separate implementation plan is warranted after the research concludes.

Phase 4 recommendation:

- The most promising next step is narrower encrypted command discovery on the existing local Encipher transport.
- Transport discovery is no longer the leading bet because all four app sessions stayed on the known port-`8833` Encipher path and did not reveal a separate upgraded stream.
- Downstream parsing or reconciliation optimization is not the first priority because the largest cost signal still comes from repeated full init-style payloads, so parser work alone would not address the main transport volume.

Ranked follow-up areas:

1. alarms and other mutation-backed pages
  - This is the highest-confidence area because Session D already proved at least one narrow action command exists.
  - The next high-value task is capturing and decoding adjacent alarm reads or detail fetches to see whether alarms also have narrower read paths.
2. overview throughput telemetry
  - This remains important, but current evidence does not yet show a distinct stream.
  - Any future work here should focus on targeted captures that force visible throughput changes while isolating overview-only behavior.
3. VPN status and network status
  - These remain plausible candidates for page-scoped reads, but there is currently less direct evidence than for alarms.
  - They should be explored after alarms or throughput only if a concrete UX or performance goal depends on them.

Recommendation on next planning step:

- A separate implementation plan is not warranted yet for production integration changes.
- A small follow-up protocol-discovery plan is warranted if this research should continue, focused on decoding page-specific read commands adjacent to already-proven narrow mutation commands.

Additional alarm-action note from the final batched capture:

- A single follow-up capture of multiple alarm actions confirmed that alarm mutations are easy to identify on the existing local Encipher transport.
- The observed command shapes were:
  - temporary mute: `alarm:allow` with an `expireTs` value and `archiveAlarmByType`
  - always mute: `alarm:allow` with match metadata but no `expireTs`
  - block: `alarm:block`
  - release from quarantine: `alarm:ignore` followed immediately by a device-targeted `mtype=set` policy write
- Practical takeaway: alarm-related actions appear to follow a straightforward and fairly standard pattern where the alarm command records the user decision and any device-state change is carried by a separate follow-up write when needed.

Additional live-throughput note from the final spot-check capture:

- A deeper raw-flow review of the live-throughput capture changed the initial read.
- On port `8833`, the capture showed sustained box-to-phone traffic for about `126` seconds rather than just one or two isolated bursts.
- The dominant response flows contained repeated plaintext markers of the form `event:liveStats` followed by encrypted `data:` payloads, which is strong evidence of a real-time event stream on the known local transport.
- The payload timing was consistent with near-continuous updates, including regular second-scale traffic while the live-throughput view stayed open.
- The quick HTTP-oriented decoder missed this because the stream content did not present as the same request-response shape as the init captures.
- Two localhost `encipher_raw` events still aligned with the pause and resume interactions, but they were not the main throughput signal.
- Practical takeaway: live throughput does appear to use a distinct real-time feed behavior on port `8833`, even though the rest of the app still reuses the large init-style snapshot model for broader page refreshes.

Additional flows-page note from the final spot-check capture:

- The flows page did not behave like a simple init-only refresh.
- The decoded request sequence included:
  - one baseline `mtype=init`
  - one `mtype=cmd` `batchAction` containing two nested `get` requests for `host` and `auditLogs`
  - one follow-up direct `mtype=get` for `auditLogs`
- In parallel, the dominant box-to-phone traffic again included sustained `event:liveStats` payloads on port `8833`, which indicates the flows page is also paired with live streaming data rather than relying only on one-shot snapshot reads.
- Practical takeaway: the flows page appears to use a hybrid model consisting of baseline snapshot state, page-specific audit or host reads, and a concurrent live-stats stream.

Additional device-activities note from the final spot-check capture:

- The per-device Activities page for `Chads Phone` did not come from the baseline runtime snapshot, which still exposed only `flowsummary` for that device.
- The app issued repeated host-scoped `batchAction` requests against target `EC:0D:51:CC:BA:BC`.
- Those batched requests included nested `get` calls for `item=appTimeUsage` with `type=host` and at least these granularities:
  - `granularity=day`
  - `granularity=hour`
- The request payload also carried an app list including `internet`, `facebook`, and the other major apps shown in the UI, which is consistent with the page showing overall internet plus per-app usage and then drilling down into one app such as Facebook.
- The day refresh, week refresh, and Facebook drill-down all appeared to reuse the same batched host-usage request family rather than relying on a generic init refresh.
- In parallel, the page still maintained sustained `event:liveStats` response streams on port `8833`.
- Practical takeaway: the device Activities page is another hybrid surface, combining page-specific historical usage reads with the same concurrent live-stats stream behavior already observed elsewhere.

Additional direct-pull note for group and user activity scope:

- A direct read-only follow-up confirmed that the same `appTimeUsage` request family is reachable outside packet capture for group and user scopes as well as host scope.
- The working targets were:
  - group scope via `type=tag` with the affiliated group id, for example `10`
  - user scope via `type=tag` with the user id, for example `21`
- For both working scopes, the response shape matched the host test and included:
  - `internetTimeUsage`
  - `appTimeUsage`
  - `appTimeUsageTotal`
  - `categoryTimeUsage`
- A comparison test using `type=user` for the same user id returned zeroed totals, which suggests the app-relevant access path is tag-oriented rather than a distinct user-type request.
- Practical takeaway: host, group, and user activity history all appear to follow the same general retrieval pattern, with the main variation being which identifier is used as the target.

Additional minimal-request note for usage-history pulls:

- A final direct-test matrix was sufficient to identify the smallest request shape that still returns predictable usage-history data.
- For stable results, the effective request shape is:
  - `message_type=get`
  - `data.item=appTimeUsage`
  - `data.type=host` for device scope or `data.type=tag` for group and user scope
  - `target=<device MAC | group id | user id>`
  - `data.begin=<unix timestamp>`
  - `data.end=<unix timestamp>`
  - `data.granularity=<day | hour>`
- The `apps` field is optional, but its presence changes the response scope in a predictable way:
  - omitted `apps` returns all available app buckets plus internet totals
  - `apps=[]` returns internet totals with empty app buckets
  - `apps=["internet"]` behaves like an internet-only summary and also leaves app buckets empty
  - `apps=["facebook"]` or another explicit subset returns filtered app buckets plus internet totals
- Omitting `begin`, `end`, or `granularity` still produced responses in some tests, but those results were partial or degenerate and should not be treated as a stable contract.
- Practical takeaway: the predictable retrieval model is a parameterized `appTimeUsage` read with explicit time bounds, explicit granularity, and an optional app filter layered on top of a shared scope-selection pattern.

Additional retention and granularity note for host usage history:

- A direct retention probe for `Chads Phone` showed that widening the request window beyond about one week padded the response with additional zero-value daily slots, but did not increase the returned totals or interval count.
- In the tested environment, the actual populated internet history for that device appeared to cover about eight non-zero daily slots even when `30d`, `60d`, or `90d` windows were requested.
- Hourly breakdowns are supported through `granularity=hour` and return populated `slots` for both one-day and seven-day windows.
- Finer granularity strings such as `minute`, `15min`, and `15m` were accepted and returned correct total usage plus device `intervals`, but they did not produce populated `slots` in the tested responses.
- Practical takeaway: the stable slot-based granularities currently confirmed are `day` and `hour`; sub-hour detail appears to be carried by interval lists rather than a separate minute-slot structure.

Additional network-scope probe note:

- A direct follow-up tested whether the same `appTimeUsage` request family could be queried for network scope using live network identifiers from `networkProfiles`.
- The tested target shapes were:
  - `type=network`, target = raw network UUID
  - `type=tag`, target = raw network UUID
  - `type=tag`, target = `intf:<network UUID>`
  - `type=network`, target = `intf:<network UUID>`
- The tested networks included both LAN and WAN interfaces.
- All tested variants returned a valid history-shaped payload with the expected top-level sections, but every tested result was fully zeroed: zero internet totals, zero app totals, zero non-zero slots, and empty device breakdowns.
- Practical takeaway: network-scope queries appear to be syntactically accepted by the local API, but there is not yet evidence in this environment that they return meaningful usage history. Treat network history as unproven until a page-scoped capture or another direct query path produces non-zero results.

Additional network-page capture note:

- A dedicated packet capture of the app's network performance page and one specific network segment page clarified the correct query family for network-scoped data.
- The network performance page used a shared baseline plus page-specific reads:
  - `mtype=init` to `target=0.0.0.0`
  - `mtype=get` `item=networkMonitorData`
  - `mtype=get` `item=events` with filters for WAN, ethernet, ping, DNS, HTTP, and overall WAN state events
  - `mtype=get` `item=internetSpeedtestResults` with explicit `begin` and `end` bounds
- The specific network segment page did not use `type=network` or `type=tag` for history queries. Instead it used the network UUID as the message target with `data.type=intf`.
- The segment-page request sequence included:
  - a `batchAction` containing `get` requests for `item=appTimeUsage`, `type=intf`, `granularity=day`, target = network UUID
  - another nested `get` for `item=appTimeUsage`, `type=intf`, `granularity=hour`, target = network UUID
  - a direct `mtype=get` for `item=intf` against the same network UUID target
  - a later `batchAction` containing `get` requests for `item=intf` and `item=flows`, both scoped to the same network UUID target, with `type=intf` on the flows request
  - a follow-up direct `mtype=get` for `item=flows`, `type=intf`, target = network UUID
- Practical takeaway: network-segment history and activity do appear to be directly addressable on the local transport, but the correct scope is `type=intf` with the network UUID as the target. The earlier zero-result direct probe was likely invalid because it used the wrong scope type.

Additional direct validation note for `type=intf`:

- A direct read-only follow-up repeated the captured request family outside packet capture using four live network UUID targets, including LAN and WAN interfaces.
- The `type=intf` follow-up confirmed that these reads are directly reachable:
  - `item=intf` returned populated interface payloads with keys such as `last30`, `last60`, `last12Months`, `newLast24`, `hosts`, `flows`, `monitoring`, `policy`, and interface addressing metadata.
  - `item=flows`, `type=intf` returned populated flow-response dictionaries with keys `count`, `flows`, and `nextTs`.
- The same direct validation still showed zeroed `appTimeUsage` results for all tested network UUIDs in both `day` and `hour` requests, even when using the same `apps` list observed in capture.
- Practical takeaway: the correct network-segment scope is definitely `type=intf`, and interface-detail plus interface-flow reads are directly reproducible. However, the non-zero `appTimeUsage` contract for network segments is still not fully proven outside packet capture in this environment. The app may rely on additional context, different bounds, or a response path the current helper does not yet reproduce exactly.

Additional speed-test and events note:

- A lower-level raw-envelope probe confirmed that both `item=internetSpeedtestResults` and `item=events` are directly queryable on the local Encipher transport even when the current helper cannot normalize the response automatically.
- `internetSpeedtestResults` returned a stable `data.results` list with per-test records that include:
  - `timestamp`
  - WAN interface `uuid`
  - `vendor`
  - `success`
  - `manual` when applicable
  - `client` metadata such as ISP and public IP
  - `server` metadata such as host, sponsor, location, and server id
  - `result` metrics including `download`, `upload`, `latency`, `jitter`, `ploss`, `dlMbytes`, and `ulMbytes`
- Practical takeaway: speed-test history is a strong direct-service candidate because the returned contract is already close to the integration's existing normalized speed-test model and clearly supports historical lists rather than only the latest result.
- `events` returned a direct `data` list rather than a nested result object and appears to be primarily a network-health and WAN-monitoring timeline rather than a generic activity feed.
- The observed event families included:
  - `event_type=state` records for `wan_state`, `overall_wan_state`, `dualwan_state`, and `dns`
  - `event_type=action` records such as `ping_RTT` and `ping_lossrate`
  - label payloads carrying WAN interface name and UUID, readiness and active flags, ping targets, DNS server details, failure lists, and threshold values such as RTT and loss-rate limits
- Practical takeaway: `events` looks most useful for future WAN-health, failover, DNS-health, and connectivity-timeline services or sensors. It does not currently look like the right base surface for device or segment traffic history.

## Validation strategy

- Research validation in this initiative means grounding claims in one of three evidence sources only:
  - repository code and checked-in utilities
  - read-only live pulls against the local box
  - targeted packet captures from the mobile app workflow
- Any claim about a local endpoint, refresh mode, or stream behavior should be marked as confirmed only when a capture or direct probe demonstrates it.
- If additional local probe helpers are created later, they should remain outside production integration code until the transport contract is understood.

## References

- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/api/client.py`
- `custom_components/firewalla_local/const.py`
- `docs/REVERSE_ENGINEERING_WORKFLOW.md`
- `.tmp/capture_runtime_inventory.py`
- `utils/pull_runtime.py`
- `utils/auth_smoke.py`
- `utils/analyze_capture.py`
- `.artifacts/runtime-pull/`
- `.tmp/`
- `djuntgen/firewalla-home-assistant`
- `shanelord01/hass-firewalla-ng`

## Findings comparison analysis: MSP integration vs Firewalla Local

This section records a grounded comparison between the MSP-based `DaneManes/hass-firewalla` integration, the current `firewalla_local` implementation, and the local-protocol capabilities confirmed during this initiative.

### Current Firewalla Local strengths

- The local integration already has stronger rule control than the MSP integration through rule-backed switches, runtime inventory, and pause or resume services.
- The current rule switches expose richer operational metadata than the MSP summary sensor model, including pause state, pause-until time, next schedule start, next schedule end, time-limit quota, and time-limit usage.
- The local integration already exposes better appliance-health data than the MSP integration through a stable system-status binary sensor with uptime, CPU, memory, disk, and WAN address attributes.
- The latest speed-test sensor already uses normalized local data and preserves useful metadata such as ISP, public IP, latency, jitter, packet loss, server details, and manual vs automatic execution.
- The current watched-user surface already goes beyond the MSP integration in one area by exposing associated devices, unique usage today, and per-app usage totals for selected users.

### Gaps where the MSP integration is still ahead on breadth

- The MSP integration exposes router-style device trackers for all devices. The local integration currently exposes watched-device connectivity only as selected binary sensors.
- The MSP integration exposes per-device total upload and total download sensors. The local integration currently keeps host byte totals in normalized runtime data but only surfaces them as watched-device attributes.
- The MSP integration exposes recent alarms as a summary sensor with recent-event attributes. The local integration currently has no alarm entities or alarm services.
- The MSP integration exposes recent per-device flows and a rules summary sensor. The local integration currently has no flow entities and no read-only rule-summary entity.

### Gaps revealed by the new local-protocol findings

- Historical usage is now the largest clear gap. The current local integration only exposes watched-user same-day usage, while the research confirmed direct `appTimeUsage` reads for device, group, and user scopes using a shared request family.
- The device Activities page data is confirmed to come from page-specific local `appTimeUsage` reads rather than from the baseline init snapshot. This means the local box supports a meaningful history surface that is not yet represented in the integration.
- Hourly historical slots are confirmed for usage history, and sub-hour detail appears in interval lists. This creates a realistic path for structured history services or helper entities without relying on speculation.
- Alarm mutations are confirmed on the local transport through narrow commands such as `alarm:ignore`, `alarm:allow`, and `alarm:block`, including quarantine-release behavior. This makes alarm actions a realistic implementation target rather than a guess.
- The local app uses a real-time `event:liveStats` stream on port `8833`. This creates a possible future path for live throughput or live activity surfaces that the current integration does not expose.

### Recommended opportunity areas

1. Usage-history service and model layer
  - Best next opportunity because the transport shape is already proven and consistent across device, group, and user scopes.
  - Strong candidate starting point: one service that accepts a scope selector, explicit time bounds, explicit granularity, and an optional app filter, and returns a stable common response format.
2. Alarm summary and alarm-action services
  - High-value because both read-side and mutation-side alarm workflows appear to exist on the known local transport.
  - Natural first surfaces are recent alarms, archive, mute temporarily, mute always, block, and release from quarantine.
3. Device tracker and traffic entities
  - Low-risk breadth improvement because the current normalized host model already includes the key fields needed for tracker and byte-count surfaces.
4. Read-only rule summary surface
  - Useful complement to rule-backed switches so users can browse discovered rules without relying only on runtime inventory markdown.
5. Flow summaries and live throughput
  - Promising, but lower priority until the narrower reads and stream payload contract are understood well enough to avoid fragile implementations.

### Design implication for usage history

- The strongest implementation starting point is a service-first design, not immediate entity sprawl.
- A common query service can unify device, group, and user history under one stable contract while the payload semantics are still being learned.
- That service should likely accept one logical scope field and resolve it internally to the confirmed Firewalla request shape:
  - device scope -> `type=host`, target = device MAC
  - group scope -> `type=tag`, target = group id
  - user scope -> `type=tag`, target = user id
- The response format should preserve both bucketed `slots` and raw `intervals`, because the research showed that day and hour views are slot-based while sub-hour detail is interval-based.

### Important constraints

- The MSP integration is still useful as a feature inventory, but not as proof of local transport behavior.
- The local integration should avoid copying the MSP pattern of very large blob attributes where possible.
- The preferred direction is selective, typed, and bounded surfaces backed by explicit service or manager logic.

## Service-first quick-win subtasks

These subtasks turn the newly confirmed local reads into bounded service surfaces first, with entity exposure deferred until the response shapes are proven stable in production code.

### Shared normalization foundation

- [x] Extend [custom_components/firewalla_local/models.py](custom_components/firewalla_local/models.py) with typed service-response models for:
  - usage-history totals, slots, and intervals
  - speed-test history records
  - WAN event timeline records
  - network interface summary and ranked-flow payloads
- [x] Add dedicated client helpers in [custom_components/firewalla_local/api/client.py](custom_components/firewalla_local/api/client.py) for the confirmed read families instead of reusing ad hoc probe logic:
  - `appTimeUsage`
  - `internetSpeedtestResults`
  - `events`
  - `intf`
  - `flows` with `type=intf`
- [x] Decide whether the `events` and speed-test methods should use a shared raw-envelope helper or endpoint-specific parsing logic, and document that choice inline in [custom_components/firewalla_local/api/client.py](custom_components/firewalla_local/api/client.py).

Implementation note:

- The client now uses a shared decrypted-data helper for local Encipher reads and keeps endpoint-specific validation at the call sites so dict-backed and list-backed payload families can share transport logic without weakening payload checks.

### Usage-history service

- [x] Extend [custom_components/firewalla_local/services.py](custom_components/firewalla_local/services.py) and [custom_components/firewalla_local/services.yaml](custom_components/firewalla_local/services.yaml) with one service-first usage-history query surface.
- [x] Make the service accept a logical scope selector and resolve it to the proven transport contract:
  - device name or id -> `type=host`, target = MAC
  - group name or id -> `type=tag`, target = group id
  - user name or id -> `type=tag`, target = user id
- [x] Require explicit `begin`, `end`, and `granularity` inputs so the initial contract stays bounded and reproducible.
- [x] Return normalized totals, slot buckets, raw intervals, and scope metadata rather than raw Firewalla blobs.
- [x] Cover the new service in [tests/components/firewalla_local/test_services.py](tests/components/firewalla_local/test_services.py) and the request-path plus snapshot normalization in [tests/components/firewalla_local/test_client.py](tests/components/firewalla_local/test_client.py).

Implementation note:

- The new `get_usage_history` service now resolves device, group, and user targets against normalized runtime inventory, issues the proven `appTimeUsage` local read with explicit `begin`, `end`, and `granularity`, and returns one bounded response envelope with scope metadata, internet totals, app totals, per-app entries, category entries, slot buckets, and interval detail.
- The existing watched-user same-day entity path remains separate for now. The new service supports today-style queries through explicit bounds without forcing the entity path to converge prematurely.

### Speed-test history service

- [x] Add a dedicated speed-test results service in [custom_components/firewalla_local/services.py](custom_components/firewalla_local/services.py) backed by the normalized coordinator snapshot path for `internetSpeedtestResults`.
- [x] Add a dedicated action service for `runInternetSpeedtest` in [custom_components/firewalla_local/services.py](custom_components/firewalla_local/services.py) and [custom_components/firewalla_local/services.yaml](custom_components/firewalla_local/services.yaml) that resolves a requested WAN selection to the confirmed `wanUUID` command payload.
- [x] Return a bounded list of normalized records with an easy latest-result default instead of only the latest speed test already exposed in sensors.
- [x] Reuse or align with the existing speed-test models in [custom_components/firewalla_local/models.py](custom_components/firewalla_local/models.py) so latest-result and service parsing do not diverge.
- [x] Add focused tests for raw response parsing and service output in [tests/components/firewalla_local/test_client.py](tests/components/firewalla_local/test_client.py), [tests/components/firewalla_local/test_models.py](tests/components/firewalla_local/test_models.py), and [tests/components/firewalla_local/test_services.py](tests/components/firewalla_local/test_services.py).

Recommended service-contract notes for implementation:

- [x] Make the action service accept exactly one WAN selector input and resolve it against the runtime WAN inventory before sending the command:
  - `wan_uuid` for deterministic automation use
  - `wan_name` for human-driven calls from the service UI
- [x] Make the action service return a response payload rather than only fire-and-forget so automations can inspect what was actually targeted. The initial response is acknowledgment-oriented, not result-oriented:
  - resolved config entry id
  - resolved WAN metadata such as UUID and display name
  - the normalized command payload that was sent
  - any immediate command acknowledgment returned by the box
- [x] Keep the actual measured result out of the action-service response unless the command path itself starts returning the completed test record. The speed result remains the responsibility of the results read path.
- [x] For the current history service, use an easy latest-result default with an optional `limit`; defer explicit `begin` and `end` inputs until a fuller history contract is actually needed.
- [x] Per-WAN history filtering is now supported because the normalized `internetSpeedtestResults` payload carries stable WAN UUID identity in the observed contract.
- [x] Shape each history record to align with the existing latest-speed-test model fields already exposed by [custom_components/firewalla_local/sensor.py](custom_components/firewalla_local/sensor.py):
  - `tested_at`
  - `download_mbps`
  - `upload_mbps`
  - `latency_ms`
  - `jitter_ms`
  - `packet_loss_percent`
  - `download_megabytes`
  - `upload_megabytes`
  - `isp`
  - `public_ip`
  - server metadata
  - `manual`
  - `success`
  - `vendor`

Implementation note:

- The latest-speed-test sensor and the new services now share one manager-owned shaping lane. The sensor still reads `integration_manager.latest_speed_test`, and the results service reads `integration_manager.get_speed_test_results()`, both of which flow through the same `_build_speed_test_result` logic over the same normalized snapshot records.

### WAN usage services

- [x] Add a dedicated WAN usage service in [custom_components/firewalla_local/services.py](custom_components/firewalla_local/services.py) and [custom_components/firewalla_local/services.yaml](custom_components/firewalla_local/services.yaml) for `monthlyDataUsageOnWans`.
- [x] Add a dedicated WAN usage history service in [custom_components/firewalla_local/services.py](custom_components/firewalla_local/services.py) backed by `last12monthlyDataUsageOnWans`.
- [x] Normalize the two response families in [custom_components/firewalla_local/models.py](custom_components/firewalla_local/models.py) so current-month daily buckets and last-12-month monthly buckets share one coherent WAN-usage model.
- [x] Resolve WAN UUIDs to stable WAN names before returning service payloads so callers do not need to understand raw interface ids.
- [x] Preserve the app-relevant structure without exposing the entire raw payload:
  - current-month daily `download` and `upload` series
  - current-month `totalDownload` and `totalUpload`
  - `monthlyBeginTs` and `monthlyEndTs`
  - last-12-month month buckets with per-WAN stats
- [x] Add focused WAN-usage service coverage in [tests/components/firewalla_local/test_services.py](tests/components/firewalla_local/test_services.py) and keep service registration expectations current in [tests/components/firewalla_local/test_init.py](tests/components/firewalla_local/test_init.py).

Implementation note:

- The current-month WAN usage path now reuses the coordinator-owned runtime payload for `monthlyDataUsageOnWans`, while the year-history path uses one direct local `get` read for `last12monthlyDataUsageOnWans`. Both service surfaces flow through the same manager-owned WAN usage shaping layer before serialization.
- The WAN usage service output now also includes human-readable UTC ISO timestamp fields alongside the raw epoch values, and year-history periods derive `begin_timestamp` and `end_timestamp` from sample coverage when the Firewalla payload omits explicit bounds.
- The system-status binary sensor now also exposes a `current_wan_usage` attribute keyed by resolved WAN name so automations can read current upload and download totals without calling a service.

### WAN events service

- [x] Add a WAN-events history service in [custom_components/firewalla_local/services.py](custom_components/firewalla_local/services.py) for the confirmed `events` timeline rather than trying to turn it into traffic history.
- [x] Start with a narrow normalized contract that focuses on the event families already confirmed in capture and raw probes:
  - `wan_state`
  - `overall_wan_state`
  - `dualwan_state`
  - `dns`
  - action events such as `ping_RTT` and `ping_lossrate`
- [x] Normalize threshold and interface metadata so future health sensors or timeline cards can reuse the same output shape.
- [x] Add focused parsing and service tests in [tests/components/firewalla_local/test_client.py](tests/components/firewalla_local/test_client.py) and [tests/components/firewalla_local/test_services.py](tests/components/firewalla_local/test_services.py).

Implementation note:

- The WAN events service now uses one direct `item=events` paged local read with `limit_count`, `limit_offset`, `parse_json`, and `reverse`, and it normalizes supported state and action families into a shared event shape with threshold data, failure targets, and nested WAN-interface status metadata. The client path was widened just enough to support list-shaped decrypted `data` payloads without disturbing the existing dict-backed reads.

### Network segment summary services

- [x] Add one service for normalized network-interface summary reads backed by `item=intf` in [custom_components/firewalla_local/services.py](custom_components/firewalla_local/services.py).
- [ ] Add one service for normalized network-segment flow reads backed by `item=flows`, `type=intf` in [custom_components/firewalla_local/services.py](custom_components/firewalla_local/services.py).
- [x] Resolve requested network segments through the runtime network inventory before issuing the local read so callers can use stable names or known ids.
- [x] Preserve the useful app-facing structures already confirmed in direct probes without exposing the full raw response:
  - `newLast24`
  - `last30`
  - `last60`
  - `last12Months`
  - ranked upload and download summaries
  - per-host totals when present
- [x] Cover these paths in [tests/components/firewalla_local/test_services.py](tests/components/firewalla_local/test_services.py), [tests/components/firewalla_local/test_client.py](tests/components/firewalla_local/test_client.py), and [tests/components/firewalla_local/test_models.py](tests/components/firewalla_local/test_models.py).

Implementation note:

- `get_network_interfaces` now resolves network selectors from runtime `networkProfiles` and `networkConfig`, issues one direct `item=intf` read per requested network UUID, and returns a bounded normalized view with interface metadata, `newLast24`, `last60`, `last30`, `last12Months`, per-host totals, and derived top upload and download host rankings.
- The current response is intentionally broad and can be heavy when queried across all segments. Real-world usage should guide a later split into narrower or more filtered network views instead of prematurely guessing the right slicing model.

### Sequencing recommendation

- [x] Implement the shared client and model normalization first so the initial services share one parsing path.
- [x] Land usage history, internet speed test, and WAN usage before WAN events and network-segment services because they are the clearest quick wins with the lowest ambiguity.
- [ ] Defer any new entities until service payloads have been validated through the existing service and model test suite and real-world usage has confirmed which views are actually worth promoting.

## Action-trigger capture follow-ups

These captures are intended to identify discrete app-originated command shapes for common user actions that are plausible future service surfaces.

### Target action captures

- [x] Capture the app action for `Test Internet Speed` and confirm whether it is a narrow command, a batch action, or a page-triggered read-plus-command sequence.
- [x] Capture `Enable social hour` and identify the exact rule or policy mutation shape behind the toggle.
- [x] Capture `Disable social hour` and compare it against the enable path to determine whether the app uses a symmetric command or a different follow-up write.

### Adjacent read-surface follow-up

- [x] Capture the WAN data-usage page for `WAN One` and `WAN Two` if the UI exposes per-WAN usage views separately from the network-segment detail already confirmed.
- [x] Compare that page against the already confirmed `intf`, `flows`, `events`, and `internetSpeedtestResults` families before assuming it needs a new protocol surface.

### Capture output goals

- [x] Save one decoded artifact that isolates the action-trigger message sequence for speed test and social hour toggles.
- [x] Record whether these actions map cleanly onto existing rule or command families already seen in prior captures.
- [x] If the WAN data-usage page is captured later, record whether it reuses the same `type=intf` target model or introduces a WAN-specific read family.

### Confirmed action-trigger findings

- A dedicated capture for `Test Internet Speed`, `Enable social hour`, and `Disable social hour` produced a decoded artifact at [.tmp/firewalla_speed_social_actions_capture.decoded.txt](.tmp/firewalla_speed_social_actions_capture.decoded.txt).
- `Test Internet Speed` was a single narrow command on the existing local Encipher transport:
  - `mtype=cmd`
  - `item=runInternetSpeedtest`
  - `value={"wanUUID": "c28e3135-0f97-4a6e-8c78-a929a82d47f3"}`
  - practical takeaway: this is a strong candidate for a direct service because the app action is already one bounded command keyed by WAN UUID
- `Enable social hour` was not a one-off toggle flag. The app issued a `batchAction` of policy mutations:
  - `mtype=cmd`
  - `item=batchAction`
  - nested `policy:create` commands
  - the full decoded batch created `13` tag-targeted policies with tags `deviceTag:31`, `deviceTag:43`, `deviceTag:25`, `deviceTag:46`, `deviceTag:50`, `deviceTag:45`, `deviceTag:36`, `deviceTag:33`, `deviceTag:51`, `deviceTag:52`, `deviceTag:53`, `deviceTag:54`, and `deviceTag:55`
  - each decoded `policy:create` payload had the same core shape: `action=block`, `purpose=social_hour`, `expire=3600`, `target=TAG`, `type=mac`, `direction=bidirection`, `autoDeleteWhenExpires=1`, empty `scope`, empty `appTimeUsage`, and one tag reference in `tag=["deviceTag:<id>"]`
  - a runtime cross-check showed those tag ids are Firewalla device-type categories rather than a dynamic per-device selection list. The relevant tag names are `tablet`, `desktop`, `tv`, `smart speaker`, `phone`, `console`, `wearable`, `personal_default`, `projector`, `tv&projector`, `entertainment_default`, `portable media player`, and `smart display`.
  - several of those categories currently have zero matching hosts in this environment, but the app still created policies for them. This strongly suggests the app builds Social Hour from a fixed personal-and-entertainment category set rather than first filtering to only currently matched devices.
  - the current host inventory does fit that interpretation overall, although some Firewalla classifications are imperfect. Examples from this environment include iPads under `tablet`, phones and watches under `phone` and `wearable`, Echo devices under `smart speaker`, and several streaming or media endpoints under `tv`, while some obviously non-entertainment systems are also currently labeled `desktop`.
  - practical takeaway: enabling social hour appears to materialize one or more temporary blocking policies rather than flipping a single global setting
- `Disable social hour` was likewise a `batchAction`, but it removed policies rather than toggling a state flag:
  - `mtype=cmd`
  - `item=batchAction`
  - nested `policy:delete` commands
  - the full decoded batch deleted `13` policies with ids `803` through `815`
  - practical takeaway: disabling social hour currently looks like cleanup of a generated policy set, which means any future service surface should likely model it as a higher-level action instead of exposing raw policy ids directly
- The capture also showed surrounding `mtype=init` refreshes before and after the action sequence, consistent with the app's broader hybrid pattern of narrow commands plus large follow-up refreshes.

### Documented Social Hour device-type set

- The current evidence supports documenting Social Hour as a generated policy bundle over a fixed Firewalla device-type set, not as a single backend-side preset toggle.
- The captured device-type set is:
  - `tablet`
  - `desktop`
  - `tv`
  - `smart speaker`
  - `phone`
  - `console`
  - `wearable`
  - `personal_default`
  - `projector`
  - `tv&projector`
  - `entertainment_default`
  - `portable media player`
  - `smart display`
- Practical takeaway: further app-side capture is unlikely to reveal a single higher-level Social Hour command if the app is already expanding the feature into explicit `policy:create` and `policy:delete` batches on the client side.

Additional WAN data-usage page note:

- A dedicated capture of the WAN data-usage page showed that it does not reuse the previously confirmed `intf` or `flows` network-segment reads.
- The page issued a distinct pair of narrow reads on the local Encipher transport:
  - `mtype=get`, `item=monthlyDataUsageOnWans`
  - `mtype=get`, `item=last12monthlyDataUsageOnWans`, `value={}`
- A direct raw follow-up confirmed the response families and wrote the decrypted artifact to [.artifacts/wan-usage-raw.json](.artifacts/wan-usage-raw.json).
- `monthlyDataUsageOnWans` returned per-WAN daily usage arrays for the current monthly window keyed by WAN UUID, with fields including:
  - `download`
  - `upload`
  - `totalDownload`
  - `totalUpload`
  - `monthlyBeginTs`
  - `monthlyEndTs`
- `last12monthlyDataUsageOnWans` returned a year-scale history with month-level detail. The response included month buckets keyed by timestamp, and each bucket carried per-WAN `stats` objects with the same download, upload, and total fields.
- Practical takeaway: the WAN usage page is a separate direct-service candidate and is not already covered by the current integration surfaces. It supports both current-month daily usage and the full-year monthly detail visible in the app.