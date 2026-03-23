# Supporting note: Phase 2 pairing sequence

## Initiative snapshot

- Initiative: Firewalla Local runtime buildout
- Focus: Phase 2 pairing sequence from QR JSON input through local credential establishment
- Purpose: Make the first Phase 2 implementation step executable without mixing protocol detail into the main plan

## Scope and non-goals

### In scope

- Define the ordered pairing path from user-provided QR JSON to a validated local credential set
- Assign each step to either async Home Assistant orchestration or tightly scoped executor work
- Keep the sequence aligned with the accepted `api/` boundary and three-tier storage contract

### Non-goals

- Invent exact Firewalla pairing endpoints, payloads, or token fields that are not yet verified
- Finalize reauth, polling, or entity behavior beyond the initial post-pair validation call
- Expand this note into a full API exception or request-signing design

## Open questions or external dependencies

1. The local Additional Pairing flow is the only pairing flow in scope for this integration; the cloud and MSP token tooling in the broader ecosystem is explicitly out of scope
2. Whether the pairing handshake returns additional durable credential material beyond the generated PEM pair and QR-derived fields
3. Which lightweight authenticated endpoint should be treated as the first post-pair success proof
4. Whether the QR `ipaddress` should be used as-is for first pairing or may be overridden in-flow before the initial handshake
5. Which exact local route is required on the target firmware: `/v1/auth/app/verify`, `/v1/encipher/auth`, or an equivalent alias

## Source material notes

- The Firewalla ecosystem exposes multiple APIs, but this integration uses only the local app pairing and local box API on LAN port `8833`
- `create-etp-token` is the relevant pairing reference line, not the MSP or fireguard token tooling
- Public upstream confirms the QR validation fields `gid`, `seed`, `license`, `ek`, and `ipaddress`
- Public upstream confirms RSA 2048 generation with PEM SPKI public keys and PEM PKCS#8 private keys
- Public upstream does not currently expose the full local verify request body in repository history, so the exact signed payload shape remains an on-device proof step
- The standalone proof script in `poc.py` therefore treats the local verify call as an on-device proof step and keeps non-QR request fields explicit rather than pretending they are fully verified

## Phase summary table

| Step group | Focus | Execution mode | Deliverable |
| --- | --- | --- | --- |
| 1 | QR ingestion and validation | Async config flow | Normalized, typed pairing input |
| 2 | Key material generation | Executor via `hass.async_add_executor_job()` | PKCS#8 private PEM and SPKI public PEM |
| 3 | Local pairing handshake | Async `aiohttp` in `api/auth.py` | Established local credential context |
| 4 | Post-pair proof and persistence | Async orchestration plus config entry write | Minimal durable connection material |

## Per-phase details with checkboxes

### Pairing sequence

Goal: Define the first executable implementation path for pairing without guessing unverified protocol details.

- [ ] In `custom_components/firewalla_local/config_flow.py`, accept raw QR JSON input in the user step, parse it in async code, and validate the required fields already treated as baseline inputs: `license`, `gid`, `seed`, `ek`, and `ipaddress`
- [ ] Normalize only the connection values needed for the first handshake, keep the full QR payload out of logs and diagnostics, and derive the Home Assistant identity anchor from `license` before any network pairing work begins
- [ ] Abort duplicates from the immutable `license` identity rather than host or IP, then convert the validated QR payload into a typed pairing input passed into the pure `api/` layer
- [ ] Offload RSA key generation and PEM serialization to `custom_components/firewalla_local/api/crypto.py` through `hass.async_add_executor_job()`; keep the executor scope limited to CPU-bound `cryptography` work
- [ ] Return the generated PKCS#8 private PEM and SPKI public PEM to the async flow code, then call a dedicated async pairing routine in `custom_components/firewalla_local/api/auth.py` using `aiohttp` against the local box on port `8833`
- [ ] Keep all network I/O async-native: the pairing routine owns request construction, endpoint invocation, and response parsing, while the Home Assistant flow only handles orchestration and error mapping
- [ ] Treat the pairing handshake as the step that establishes usable local credentials; persist only the minimal confirmed durable material in `ConfigEntry.data`: `license`, `gid`, `ipaddress`, generated PEM values, and any additional credential artifact only if the protocol proves it is required for reconnect
- [ ] Immediately perform one lightweight authenticated follow-up call through `custom_components/firewalla_local/api/client.py` to prove the new credential context works before creating the config entry; if that proof fails, surface a flow error instead of storing half-complete connection state

### Async and executor boundary rules

- Async Home Assistant code owns QR intake, duplicate detection, unique ID assignment, config-entry creation, and API exception to flow-error mapping
- Executor work is limited to RSA generation and PEM serialization; do not move HTTP transport, config-entry writes, or Home Assistant orchestration into the executor
- Async `api/` code owns local pairing HTTP calls, response parsing, and the first authenticated proof call

## Validation strategy

- Prove the local verify call with `poc.py` against a physical box before changing `custom_components/firewalla_local/config_flow.py`
- Prove the pairing path first with pure `api/` tests for QR-to-request shaping, crypto handoff boundaries, pairing response parsing, and post-pair proof-call success or failure
- Add config-flow tests only after the pure `api/` contract is stable enough to mock without ambiguity
- Keep validation focused on sequence correctness, secret handling, and storage boundaries rather than speculative endpoint coverage

## References

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_IN-PROCESS.md`
- `plans/completed/PLATINUM_FOUNDATION_DOCS_SUP_PROTOCOL_AND_ARCH_TRAPS.md`
- `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla_local/api/auth.py`
- `custom_components/firewalla_local/api/client.py`
- `custom_components/firewalla_local/api/crypto.py`
- `poc.py`