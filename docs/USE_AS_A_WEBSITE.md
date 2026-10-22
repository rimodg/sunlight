# Use SUNLIGHT as a hosted website

The hosted configuration runs the working application and API together. It does
not serve the PDF as the product. The home address opens the evidence workspace.

## One-time hosting account step

1. Sign into [Render](https://dashboard.render.com/) and connect your GitHub
   account so it can read `rimodg/sunlight`.
2. Choose **New**, then **Blueprint**, and select `rimodg/sunlight`.
3. Select branch **codex/sunlight-hosted-access**. Review `render.yaml`.
4. The prepared service selects the **free** plan. Confirm availability and
   account requirements in Render before deploying. Do not accept a paid plan
   unless you choose its charges.
5. Deploy the blueprint and wait for the service to show **Live**.
6. Open the service's assigned HTTPS address. Your browser asks you to sign in.
   Username: `sunlight`. Retrieve the generated `SUNLIGHT_ACCESS_PASSWORD` in
   that Render service's **Environment** settings. Do not paste it in chat.

The assigned address is your application URL. No Docker or terminal commands
are needed on your computer. There is no live address until your hosting account
has actually deployed the service.

## First use

Choose **Direct award above threshold**, then **Analyze supplied evidence**.
Inspect the finding, missing inputs, and calculation trace. Download the evidence
packet. Then use a public OCDS-shaped record, selecting the appropriate
jurisdiction and currency.

## What this deployment provides

- HTTPS is supplied by the hosting platform.
- A personal password gate covers the workspace, assets, API, and documentation.
- Health checks remain public so the host can check readiness.
- Startup fails if authentication is required but its password is missing.
- The container packages the interface and API together; CI includes a live
  container integration job.

This personal gate is not institutional SSO, user roles, or an audit identity
system. Free hosting may sleep when idle and has provider resource limits.
Calibration observations and in-memory state are not durable institutional
records. Retain downloaded evidence packets yourself. Use public or synthetic
data until the appropriate data-handling and deployment controls are established.

Keep the deployment branch available. After merging the hosted configuration,
switch Render to `main` before deleting that branch. A GitHub commit or Codex
environment publication does not itself deploy the Render service.

## Global watch and country research

Search a country by name or ISO code to zoom and hold its map, then open the
documented total for categories, source-document references and completion gaps.
Return to the global view to resume rotation. The published procurement card provides source-pinned country-year values on
opening. Its source register and year selector are separate from your analyzed
inputs; neither represents complete national procurement coverage. All 250
countries and territories remain selectable, including uncovered places.

**Trade data & sources** shows the dated UN Comtrade preview's availability,
coverage and query links. It may remain unavailable if the provider rejects or
limits requests. No illustrative routes are substituted. The annual procurement
context counter stays unavailable until a cited baseline is configured; see
[data sources and configuration](GLOBAL_WATCH_DATA.md).

## Persistent operations pilot

The website now opens on **Operations desk**. Register a source with an explicitly selected calibration profile, submit cumulative versioned source snapshots, open a case, follow it and save a review note. The desk compares due, same-unit/same-period measurements and saves available engine results. **Global watch** retains the globe and prior session analysis tools. Source records are not preloaded or invented.

Use [the operational schema and workflow](OPERATIONS_PILOT.md) for the API, connector client and deployment requirements. Before retaining institutional records on Render, attach a persistent disk and set `SUNLIGHT_OPERATIONS_DB` to a writable path on that disk. Without it, this pilot's SQLite ledger can disappear on redeploy. The feature is an attributed push API; no live UN connection, proprietary source mapping or institutional SSO has been activated.
