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
Return to the global view to resume rotation. Procurement totals reflect your
current analyzed inputs, not complete national procurement coverage.

**Trade data & sources** shows the dated UN Comtrade preview's availability,
coverage and query links. It may remain unavailable if the provider rejects or
limits requests. No illustrative routes are substituted. The annual procurement
context counter stays unavailable until a cited baseline is configured; see
[data sources and configuration](GLOBAL_WATCH_DATA.md).
