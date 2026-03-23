# Initiative Plan: Firewalla Local security docs

## Initiative snapshot

- Initiative: Firewalla Local security docs
- Status: In process
- Owner: Firewalla Strategist
- Primary outcome: Define the implementation plan for adding a root `SECURITY.md` with ChoreOps-style vulnerability reporting procedures while making `docs/ARCHITECTURE.md` the durable home for Firewalla Local's high-level security model, trade-offs, and awareness notes.
- Why now: The repository is private during buildout but is expected to become public later. It does not yet have a root security policy and it does not yet make the security posture explicit inside the architecture foundation document. The requested write-up is directionally correct, but several statements need a factuality pass and a clear disclaimer posture before they become durable repository promises.

## Scope and non-goals

### In scope

- Add a root `SECURITY.md` in `/workspaces/firewalla-local-ha/`.
- Reuse the standard ChoreOps vulnerability reporting flow as the baseline for reporting procedures.
- Add a high-level security section to `/workspaces/firewalla-local-ha/docs/ARCHITECTURE.md` that explains the split cloud-provisioning and local-runtime model plus the relevant security implications.
- Update both `SECURITY.md` and `README.md` to point readers to `docs/ARCHITECTURE.md` for the architectural security approach and awareness notes.
- Audit the requested wording against the current repo state so the final docs distinguish verified behavior from planned behavior.
- Add explicit public-facing disclaimer language covering independent status, lack of Firewalla affiliation or support, and use-at-your-own-risk expectations.
- Identify any related doc updates required in `README.md`, `docs/ARCHITECTURE.md`, and `custom_components/firewalla_local/quality_scale.yaml` comments.

### Non-goals

- Do not change runtime behavior, config-entry storage, diagnostics logic, or logging code as part of this documentation initiative.
- Do not claim security guarantees that are not implemented or verified in the current repository.
- Do not introduce a separate security contact process unless the repository owner explicitly chooses one.
- Do not add marketing language or security claims beyond what the repo can defend technically.
- Do not duplicate the full architecture narrative across `SECURITY.md`, `README.md`, and `docs/ARCHITECTURE.md`.
- Do not write the security model as if it were endorsed by, reviewed by, or supported by Firewalla.

## Open questions or external dependencies

1. Should the repository use only GitHub private vulnerability reporting, matching ChoreOps, or should it publish an additional fallback contact path such as an email address?
2. Which statements from the proposed write-up are verified today versus only supported by the PoC and architecture docs?
3. Should the final architecture text explicitly state that local runtime uses encrypted payloads over HTTP, rather than implying transport-layer security?
4. Is the replay-protection claim fully verified for the integration implementation, or only inferred from observed message structure in `poc.py` and the current API client envelope?
5. Is there any repo-level policy preference on response timelines beyond the ChoreOps defaults of 7-day acknowledgement and 14-day triage?

Resolved direction from repository owner:

- The repository is expected to become public later, so the final docs must read as public-facing repository documentation rather than private team notes.
- The architecture and security write-up should be framed as the maintainer's view of the design and risks, not as a vendor-authored or vendor-approved statement.
- The docs should include clear disclaimers that the project is independent, not associated with Firewalla, not supported by Firewalla, and should be used at the reader's own risk.

## Phase summary table

| Phase | Focus | Deliverable | Notes |
| --- | --- | --- | --- |
| 1 | Baseline and claim audit | Verified claim matrix for security documentation | Prevents inaccurate or overstated guarantees |
| 2 | Architecture security section | Final `docs/ARCHITECTURE.md` security-content plan | Makes the security model part of the integration foundation |
| 3 | Reporting doc and cross-links | `SECURITY.md` and `README.md` pointer plan | Keeps reporting separate from architecture |
| 4 | Validation and builder handoff | File-by-file documentation task list | Supports a clean implementation pass |

## Per-phase details with checkboxes

### Phase 1: Baseline and claim audit

Goal: Convert the requested prose into a verified claim set before any repository-facing security document is written.

- [x] Use `/workspaces/choreops/SECURITY.md` as the baseline for reporting procedure language and keep the Firewalla repo aligned with that structure unless a repository-specific need forces a deviation.
- [x] Compare the requested security overview against the current durable sources:
  - `/workspaces/firewalla-local-ha/docs/ARCHITECTURE.md`
  - `/workspaces/firewalla-local-ha/docs/DEVELOPMENT_STANDARDS.md`
  - `/workspaces/firewalla-local-ha/README.md`
  - `/workspaces/firewalla-local-ha/custom_components/firewalla_local/api/client.py`
  - `/workspaces/firewalla-local-ha/custom_components/firewalla_local/diagnostics.py`
  - `/workspaces/firewalla-local-ha/poc.py`
- [x] Mark each requested claim as one of:
  - verified in current implementation
  - verified only in PoC or architecture evidence
  - planned but not yet implemented
  - unsupported and should be removed or softened
- [x] Pay specific attention to these claims, which are the highest risk for accidental overstatement:
  - replay-attack protection via timestamps and message identifiers
  - strict log sanitization in runtime code
  - exact revocation workflow and wording around paired-device removal
  - whether cloud use is only during provisioning for the implemented integration, not just for the PoC and architecture plan
- [x] Decide the wording strategy for claims that are directionally correct but not yet fully enforced in code, such as using "designed to," "the current architecture expects," or "the implementation aims to" where needed.
- [x] Define the disclaimer style for public release so it is clear but not alarmist:
  - independent community project
  - not affiliated with, endorsed by, or supported by Firewalla
  - use at your own risk
  - architecture discussion reflects the maintainer's technical view, not vendor documentation

### Phase 2: Architecture security section

Goal: Define the exact content and structure of the security-oriented architecture additions in `docs/ARCHITECTURE.md`.

- [x] Add a dedicated high-level security section to `docs/ARCHITECTURE.md` that covers:
  - split architecture: cloud-brokered provisioning and local runtime
  - local runtime over LAN port `8833`
  - application-layer encryption of request and response payloads
  - config-entry storage trade-offs in Home Assistant
  - diagnostics and log redaction expectations
  - recommended deployment posture and VLAN segmentation guidance
- [x] Add a short disclaimer block near the architecture security section that makes the repository posture explicit for future public readers:
  - this is an independent integration
  - it is not associated with or supported by Firewalla
  - the guidance reflects the maintainer's interpretation of the protocol and trade-offs
  - users are responsible for evaluating and operating it at their own risk
- [x] Place the new section so it reads as part of the core architecture posture, not as an appendix disconnected from the integration design.
- [x] Ensure the architecture doc distinguishes transport security from payload encryption, so the document does not imply HTTPS where only encrypted HTTP payloads exist.
- [x] Ensure the architecture doc avoids unsupported absolutes such as "never" or "strictly prohibited" unless the current codebase enforces them today.
- [x] Keep implementation-detail rules in `docs/DEVELOPMENT_STANDARDS.md` and keep `docs/ARCHITECTURE.md` focused on the user-relevant and design-relevant security model.

### Phase 3: Reporting doc and cross-links

Goal: Keep `SECURITY.md` focused on vulnerability reporting while using `README.md` and `SECURITY.md` to route readers to the architecture document for the security model.

- [x] Create a concise root `SECURITY.md` structured around reporting procedures only:
  - do not report vulnerabilities publicly
  - use GitHub private vulnerability reporting via the Security tab
  - fallback instruction if private reporting is unavailable
  - what to include in a report
  - response expectation targets
  - repository scope statement
  - pointer to `docs/ARCHITECTURE.md` for the high-level security approach and awareness notes
- [x] Add a brief non-affiliation note in `SECURITY.md` if needed so public readers do not confuse the reporting policy with an official Firewalla support channel.
- [x] Adapt the repository scope statement so it applies to Firewalla Local and its maintained releases rather than ChoreOps.
- [x] Update `README.md` to add a concise security pointer that explains where users should read about:
  - vulnerability reporting
  - the high-level security approach
  - security trade-offs and awareness notes
  - the split provisioning and local-runtime model
- [x] Add a short public-facing disclaimer in `README.md` or the nearest appropriate intro section so the independent and unsupported status is visible before users treat the repo as an official integration.
- [x] Verify that `docs/ARCHITECTURE.md` becomes the source of truth for the high-level security model and that `SECURITY.md` does not duplicate that narrative.
- [x] Verify that `docs/DEVELOPMENT_STANDARDS.md` still owns prescriptive coding and secret-handling rules, while `SECURITY.md` remains repository-facing and reporting-focused.
- [x] Review `custom_components/firewalla_local/quality_scale.yaml` comments for any doc-related notes that should reference the existence of `SECURITY.md` once it is added.
- [x] Remove or soften wording duplication if the same security claim would otherwise appear in multiple docs with different confidence levels.

### Phase 4: Validation and builder handoff

Goal: Produce the implementation-ready documentation task list and acceptance criteria.

- [x] Define the exact implementation surface:
  - `/workspaces/firewalla-local-ha/SECURITY.md`
  - `/workspaces/firewalla-local-ha/README.md`
  - `/workspaces/firewalla-local-ha/docs/ARCHITECTURE.md`
  - optional follow-up edits in `/workspaces/firewalla-local-ha/custom_components/firewalla_local/quality_scale.yaml`
- [x] Define acceptance criteria for the final docs:
  - the repo has a root `SECURITY.md`
  - reporting procedures match the standard ChoreOps private-reporting posture unless intentionally changed
  - `docs/ARCHITECTURE.md` contains the high-level security approach and awareness notes
  - the architecture security narrative is technically accurate for the current repo state
  - public readers can clearly tell that the project is independent and not vendor-supported
  - the document clearly separates verified behavior from architecture intent where needed
  - both `SECURITY.md` and `README.md` point users to `docs/ARCHITECTURE.md` without duplicating the full architecture narrative unnecessarily
- [x] Define a short implementation note for the builder that any wording copied from the proposed write-up must be normalized for technical precision before merge.
- [x] Record any unresolved claims as explicit follow-up items rather than burying them inside prose.
- [x] Use the defined handoff to `Firewalla Builder` once the reporting-contact choice is confirmed.

## Execution outcome

Implemented in this phase:

- added `/workspaces/firewalla-local-ha/SECURITY.md` with reporting-only policy content based on the ChoreOps baseline
- added a high-level security posture section and a public-facing disclaimer to `/workspaces/firewalla-local-ha/docs/ARCHITECTURE.md`
- updated `/workspaces/firewalla-local-ha/README.md` with an independent-project disclaimer and doc pointers
- reviewed `/workspaces/firewalla-local-ha/custom_components/firewalla_local/quality_scale.yaml` and left it unchanged because this phase did not alter quality-scale status claims

Residual documentation risks to keep visible:

- replay-attack behavior is described conservatively because the repository evidence supports message timestamps and IDs, but this plan does not claim a complete replay-defense proof
- pairing revocation guidance is intentionally high-level because mobile-app menu text can change over time
- the docs describe the maintainer's current technical view and should be revisited if protocol evidence changes during implementation

## Validation strategy

This is a documentation-planning initiative, so no lint, type-check, or test execution is required at the planning stage.

- The plan must remain consistent with `/workspaces/firewalla-local-ha/docs/ARCHITECTURE.md` and `/workspaces/firewalla-local-ha/docs/DEVELOPMENT_STANDARDS.md`.
- The plan must preserve the current ChoreOps-style vulnerability reporting baseline unless the repository owner chooses a different contact model.
- The plan must avoid turning PoC evidence into unconditional product guarantees without a verification pass.
- The plan must keep the high-level security model in `docs/ARCHITECTURE.md` and keep `SECURITY.md` focused on reporting procedures plus pointers.
- The plan must treat security documentation as a factual contract with users, not as aspirational marketing copy.
- The plan must make the public-facing non-affiliation and use-at-your-own-risk posture obvious enough that readers do not mistake the repository for an official Firewalla project.

## References

- `/workspaces/firewalla-local-ha/AGENTS.md`
- `/workspaces/firewalla-local-ha/README.md`
- `/workspaces/firewalla-local-ha/docs/ARCHITECTURE.md`
- `/workspaces/firewalla-local-ha/docs/DEVELOPMENT_STANDARDS.md`
- `/workspaces/firewalla-local-ha/custom_components/firewalla_local/manifest.json`
- `/workspaces/firewalla-local-ha/custom_components/firewalla_local/config_flow.py`
- `/workspaces/firewalla-local-ha/custom_components/firewalla_local/api/client.py`
- `/workspaces/firewalla-local-ha/custom_components/firewalla_local/diagnostics.py`
- `/workspaces/firewalla-local-ha/custom_components/firewalla_local/quality_scale.yaml`
- `/workspaces/firewalla-local-ha/poc.py`
- `/workspaces/choreops/SECURITY.md`