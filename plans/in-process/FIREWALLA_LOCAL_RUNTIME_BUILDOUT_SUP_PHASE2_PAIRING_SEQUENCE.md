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
2. Whether the authenticated cloud link step ever requires fields beyond the decrypted QR pairing object and the bearer token from `login/eptoken`
3. Which cloud group-list endpoint the mobile app prefers after linking, even though `login/eptoken` already returns enough group data for a fallback implementation
4. Whether the QR `ipaddress` should be treated as informational only in Home Assistant and replaced by a LAN override whenever it resolves to the public address instead of the local box
5. Which lightweight authenticated post-link message should be treated as the first local runtime success proof beyond the current `init` handshake

## Source material notes

- The Firewalla ecosystem exposes multiple APIs, but this integration uses only the mobile-app cloud provisioning flow plus the local box API on LAN port `8833`
- `create-etp-token` is the relevant pairing reference line, not the MSP or fireguard token tooling
- Public upstream confirms the QR validation fields `gid`, `seed`, `license`, `ek`, and `ipaddress`
- Public upstream confirms RSA 2048 generation with PEM SPKI public keys and PEM PKCS#8 private keys
- Mobile app logs show the joining device establishes its ETP identity first with `POST /app/api/v2/login/eptoken`
- The QR `ek` payload decrypts into the pairing object consumed by the cloud link step, centered on the rendezvous identifier and license payload
- Public upstream and the successful standalone proof both point to `POST /app/api/v2/ept/rendezvous/me` as the authenticated cloud link step
- The box appears in the linked group list only after the cloud link step completes, and the durable symmetric key is then decrypted from `symmetricKeys[0].key`
- Local `http://{localIp}:8833/v1/encipher/message/{gid}` traffic is post-link runtime initialization, not the first-time provisioning handshake
- The successful standalone proof in `poc.py` now verifies the whole split flow: cloud identity, cloud link, group discovery, symmetric-key recovery, and local `init`

## Phase summary table

| Step group | Focus | Execution mode | Deliverable |
| --- | --- | --- | --- |
| 1 | QR ingestion and validation | Async config flow | Normalized, typed pairing input |
| 2 | Key material generation | Executor via `hass.async_add_executor_job()` | PKCS#8 private PEM and SPKI public PEM |
| 3 | Cloud provisioning handshake | Async `aiohttp` in `api/auth.py` | Linked group plus decrypted durable key |
| 4 | Local runtime handoff and persistence | Async orchestration plus config entry write | Proven local credential context |

## Per-phase details with checkboxes

### Pairing sequence

Goal: Define the first executable implementation path for pairing without guessing unverified protocol details.

- [x] In `custom_components/firewalla_local/config_flow.py`, accept raw QR JSON input in the user step, parse it in async code, and validate the required fields already treated as baseline inputs: `license`, `gid`, `seed`, `ek`, and `ipaddress`
- [x] Normalize only the connection values needed for the first handshake, keep the full QR payload out of logs and diagnostics, and derive the Home Assistant identity anchor from `license` before any network pairing work begins
- [x] Abort duplicates from the immutable `license` identity rather than host or IP, then convert the validated QR payload into a typed pairing input passed into the pure `api/` layer
- [x] Offload RSA key generation and PEM serialization to `custom_components/firewalla_local/api/crypto.py` through `hass.async_add_executor_job()`; keep the executor scope limited to CPU-bound `cryptography` work
- [x] Return the generated PKCS#8 private PEM and SPKI public PEM to the async flow code, then call a dedicated async pairing routine in `custom_components/firewalla_local/api/auth.py` that performs the cloud provisioning steps with `aiohttp`: `login/eptoken`, QR decrypt, authenticated link, and group polling
- [x] Keep all network I/O async-native: the pairing routine owns request construction, endpoint invocation, response parsing, and bearer-token handling, while the Home Assistant flow only handles orchestration and error mapping
- [x] Treat the cloud provisioning handshake as the step that establishes usable durable credentials; persist only the minimal confirmed durable material in `ConfigEntry.data`: `license`, `gid`, a validated local IP, generated PEM values, and the decrypted group symmetric-key artifact only if reconnects prove it is required
- [x] Immediately perform one lightweight authenticated follow-up call through `custom_components/firewalla_local/api/client.py` against the local box on `8833` to prove the new runtime credential context works before creating the config entry; if that proof fails, surface a flow error instead of storing half-complete connection state

## Execution outcome

This support slice is now implemented in the live repository:

- the integration accepts raw QR JSON in config flow and validates it through the real `api/` helpers
- the Home Assistant unique ID is anchored to `license`
- RSA generation stays on the executor boundary while all HTTP work remains async-native
- cloud bootstrap and local runtime proof now run through the real `firewalla_local` modules rather than the standalone PoC only
- reauth uses the same verified pairing path with a fresh QR payload
- the bounded `auth_smoke.py` tool now exercises the integration modules directly for live protocol validation

Open protocol risk that remains after this phase:

- the runtime read path is verified, but the local write path for rule mutation is still not fully confirmed

### Async and executor boundary rules

- Async Home Assistant code owns QR intake, duplicate detection, unique ID assignment, config-entry creation, and API exception to flow-error mapping
- Executor work is limited to RSA generation and PEM serialization; do not move HTTP transport, config-entry writes, or Home Assistant orchestration into the executor
- Async `api/` code owns cloud provisioning HTTP calls, group-response parsing, the local runtime proof call, and any safe local-IP override logic

## Validation strategy

- Prove the split cloud-plus-local flow with `poc.py` against a physical box before changing `custom_components/firewalla_local/config_flow.py`
- Prove the pairing path first with pure `api/` tests for QR-to-request shaping, crypto handoff boundaries, cloud-link response parsing, group bootstrap extraction, and post-link local proof-call success or failure
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