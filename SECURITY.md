# Security Policy

## Posture

SUNLIGHT is institutional procurement integrity verification infrastructure
currently in pre-deployment development. This policy establishes the
vulnerability handling posture in preparation for institutional deployment.
It is shaped by the EU Cyber Resilience Act (Regulation EU 2024/2847),
whose Article 14 reporting obligations apply from 11 September 2026.

## Supported versions

SUNLIGHT is currently at version 0.x (pre-release). No stable release
series exists yet. When the first stable release is tagged, supported
version status will be documented here.

| Version | Supported |
|---------|-----------|
| 0.x (current main branch) | Yes — active development |

## Reporting a vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Use GitHub's private security advisory mechanism:
https://github.com/rimodg/sunlight/security/advisories/new

If the advisory mechanism is not available, email:
rimwayamohamedouedraogo@gmail.com with subject line [SUNLIGHT SECURITY]

You will receive an acknowledgment within 24 hours of submission.

## Response timeline

These timelines are calibrated to the CRA Article 14 shape and reflect
an unconditional operational commitment:

- Acknowledgment: within 24 hours of a report, we confirm receipt and
  state whether we consider it a credible vulnerability.
- Full assessment: within 72 hours of a credible actively-exploited
  vulnerability report, we provide impact scope, affected versions, and
  all available mitigation guidance.
- Final disclosure: no later than 14 days after a corrective measure is
  available, we publish root cause, impact scope, and patch details.

## Design properties that bound the attack surface

SUNLIGHT is built to minimize the exposure an institution takes on when
deploying it:

- **Stateless by design.** The analysis service holds no persistent state.
  Contract data enters, case packets exit. Nothing is stored between
  requests. An institution running SUNLIGHT inside its own network boundary
  never exposes its contract data to an external service.
- **No model in the analytical path.** The detection engines (CRI, TCA,
  EVG, all five sides) are fully deterministic rule-based systems. No LLM,
  no stochastic component. Same input, same output, on any machine. This
  eliminates the entire class of vulnerabilities specific to model
  inference paths.
- **Authentication at the boundary.** The API is designed for deployment
  behind the institution's own authentication layer. The analysis service
  is internally stateless; authentication is an infrastructure concern at
  the deployment boundary, not baked into the analysis code.
- **Pinned dependency surface.** Runtime dependencies are fastapi, uvicorn,
  pydantic, httpx, numpy, scipy, networkx, requests, and pdfplumber. Exact
  pinned versions with transitive resolution are in requirements.lock in
  this repository.

## Scope

**In scope:** the SUNLIGHT API (code/), all detection engines, the Absence
Ledger, the Docker container image, and this repository's GitHub Actions
workflows.

**Out of scope:** infrastructure the institution operates in front of
SUNLIGHT, the institution's own contract data, and third-party upstream
dependencies. Vulnerabilities discovered in third-party components will be
reported to their maintainers per CRA's upstream notification obligation.

## CRA commitment (Article 14, Regulation EU 2024/2847)

When SUNLIGHT is placed on the EU market, we commit to:

- Reporting actively exploited vulnerabilities to ENISA through the CRA
  Single Reporting Platform within the mandated 24-hour early warning and
  72-hour full notification windows.
- Notifying affected users and, where appropriate, all users, without
  undue delay of vulnerabilities and available corrective measures.
- Notifying upstream component manufacturers of vulnerabilities discovered
  in their components.
- Maintaining a software bill of materials covering at minimum top-level
  dependencies. See requirements.lock. Full SBOM in CycloneDX or SPDX
  machine-readable format will accompany the first stable release.

## Disclosure policy

We follow coordinated disclosure: reporters are asked to give us reasonable
time to investigate and remediate before public disclosure. We will not
take legal action against researchers who report in good faith through the
channels above and who do not exploit vulnerabilities beyond what is
necessary to demonstrate the issue.
