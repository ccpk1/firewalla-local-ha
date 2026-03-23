# Supporting note: protocol and architecture traps

## Purpose

This note captures the critical protocol realities and planning traps that must shape the documentation foundation and the next runtime architecture plan.

## Verified findings from upstream research

### Pairing is local-only for this integration path

- The first-time ETP pairing flow used by this integration path is local-only.
- The QR payload contains pairing data such as `gid`, `seed`, `license`, `ek`, and `ipaddress`.
- The pairing step is treated as a LAN handshake against the box on port `8833`.
- The architecture should model this as `crypto_utils.py` plus a local authentication flow, not as a cloud rendezvous workflow.

### Local box communication is standard signed REST

- Once credential material is generated, the local box accepts standard HTTP GET and POST requests on port `8833`.
- The requests are authenticated and cryptographically signed using the generated ETP PEM material.
- The Home Assistant integration should treat the API layer as an async local REST client built on `aiohttp`.

### Local rule endpoints are verified enough for MVP planning

- Community tooling has successfully queried and parsed local rule data for years.
- The architecture can confidently plan around local rule polling in the coordinator.
- Remaining uncertainty is narrower: exact mutation semantics, filtering strategy, and how much of the broader local API belongs in the MVP.

## Opportunities

### Opportunity 1: Build the foundation around a clean local REST boundary

The architecture docs can already be precise about layering even before all rule commands are known:

- crypto/key material generation
- local pairing and token establishment
- signed REST transport
- domain managers for rules and other future capabilities
- Home Assistant wiring layer

### Opportunity 2: Use initialization payloads as the first discovery surface

The initialization response already appears to expose:

- rule groups
- policy rules
- exception rules
- screen-time rules
- hosts
- feature flags

That creates a realistic path for MVP discovery and state sync even before every mutation command is mapped.

### Opportunity 3: Keep the reusable client boundary internal first

The user-facing architecture goal of a separate client layer is sound, but the repo does not need a premature PyPI split now. The docs should define an internal pure `api/` submodule boundary inside the integration package and defer any external packaging question indefinitely.

### Opportunity 4: Bake Home Assistant reauth behavior into the architecture now

The protocol already implies a credential lifecycle. If the docs define the `401 Unauthorized` path now, later implementation can cleanly map persistent authentication failure into Home Assistant reauth instead of ad hoc retry loops.

## Traps

### Trap 1: Overcomplicating the local API transport

If the docs assume an encipher-message transport layer instead of a standard local REST client, the architecture will be more complex than needed and the implementation plan will start from the wrong primitives.

### Trap 2: Using PEM shape as the success metric

Matching the visual structure of generated PEM files is not enough. The real acceptance criteria are:

- successful local pairing flow
- successful local token establishment
- successful authenticated local REST requests
- successful local rule retrieval and mutation against the box

### Trap 3: Locking the repo into the wrong package/domain naming too early

The repo currently uses `custom_components/firewalla/`, while the high-level concept mentions `custom_components/firewalla_local/` and `firewalla_local_api/`. That mismatch needs an explicit decision before the architecture docs normalize one direction.

### Trap 4: Allowing `api.py` to become the protocol monolith

If crypto utilities, PEM handling, signing, token lifecycle, and HTTP session behavior all land in one `api.py` file, the first real implementation pass will create a maintenance problem immediately. The architecture docs should require a pure `api/` submodule with separate modules for client, crypto, auth, and transport concerns.

### Trap 5: Assuming the options flow can be designed before the rule identity model is known

The MVP wants switch entities for selected rules. That requires verified answers for:

- stable rule identifier fields
- friendly display name derivation
- rule type filtering
- pause/resume semantics
- mutation success confirmation after app-side changes

The docs should call these out as required inputs to the next runtime plan.

### Trap 6: Missing the Home Assistant reauth lifecycle

If pairing is revoked in the Firewalla app or firmware invalidates the local credentials, the coordinator must not fail forever. The architecture docs need an explicit rule that persistent `401 Unauthorized` responses transition into the Home Assistant reauthentication flow.

For this repo, that rule is now concrete: one immediate retry after the first `401`, then raise `FirewallaAuthError`, then let the Home Assistant layer raise `ConfigEntryAuthFailed`.

### Trap 7: Using IP address as the device identity

Home Assistant device and entity identity must survive network changes. The architecture docs need an explicit rule that the immutable device identifier comes from stable box data such as `gid` or another QR-derived identifier, never from the current host or IP.

For this repo, that rule is now concrete: use `license` as the immutable registry identity and treat `gid` as a connection parameter only.

### Trap 8: Assuming the standard library is enough for the crypto layer

The crypto/token work likely requires an external dependency such as `cryptography`. If the docs avoid stating that requirement up front, the eventual implementation will either drift into unsupported hacks or add undeclared manifest requirements late.

### Trap 9: Porting Node semantics too literally into Home Assistant

The upstream Node code is valuable as a protocol reference, but the Home Assistant implementation must remain:

- async-native
- typed
- secret-safe
- coordinator-friendly
- config-entry-aware

The architecture docs should borrow protocol knowledge, not runtime coding style.

## Recommended impact on the next runtime architecture plan

The follow-on plan should start with a protocol-proof phase, not with Home Assistant entity work.

Recommended early execution order:

1. Cryptography parity and local pairing proof
2. Local token establishment proof
3. Signed local REST client proof
4. Immutable device identity proof
5. Rule discovery proof
6. Rule mutation proof
7. Home Assistant config flow and reauth integration
8. Coordinator and entity architecture

## Documentation implications now

The new `docs/ARCHITECTURE.md` and `docs/DEVELOPMENT_STANDARDS.md` should:

- distinguish verified and provisional feature details without downgrading the verified local REST transport model
- describe the API layer as a signed local REST client
- require a pure internal `api/` submodule instead of a monolithic `api.py`
- define a persistent-`401` to reauth handoff rule
- define the immutable non-IP unique ID strategy for the device registry
- note the need for an external cryptography dependency and manifest alignment
- require secret-safe handling of QR payloads, private keys, and tokens
- avoid promising a specific rule manager interface until the commands are verified