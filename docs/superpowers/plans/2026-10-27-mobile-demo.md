# Mobile camera demo implementation plan

**Goal:** Publish the supplied red/yellow design as a phone-friendly HTTPS demo,
with actual recognition performed by the existing local GPU pipeline.

**Architecture:** Static HTML/CSS/ES modules on Vercel; same-origin Node gateway
with an access-code exchange for an eight-hour HttpOnly cookie. Gateway forwards
only allowlisted requests to an authenticated local FastAPI bridge through an
outbound Cloudflare Quick Tunnel. The normal loopback-only demo remains separate.

**Tech stack:** Existing Python/PyTorch/FastAPI, Node 24 standard APIs and node:test;
no frontend framework or additional database. Vercel connected-account tools.

**Authorization:** User requested autonomous configuration and publication, supplied
the design, and authorized using this PC as backend. No design-approval round is
needed. Vercel team consent remains an explicit provider-controlled user action.

## Decisions and constraints

- Reuse the existing working checkout branch/data in the original checkout; create
  a new feature branch before committing. Implementation staging is the writable
  workspace. Separate worktree would lack the ignored GPU/data artifacts needed here.
- A paid GPU/cloud service, custom domain and router/firewall changes are unnecessary.
- HTTPS is required for getUserMedia. Provide native camera/file capture fallbacks.
- Always label experimental model, simulated receipt and fictitious prices.
- Require review and ACK for every addition; camera capture does not charge anyone.
- Resize client images to 1600px and below1.5MB; gateway limits requests to2MB.
- Keep backend credential/server signing secret out of client assets and Git.
- Temporary tunnel is suitable for presentation and needs a running PC/process.

## Tasks

- [x] Backend bridge: add tests for absent/wrong credentials, Host/Origin and closed
  routes, then a constant-time token boundary. Launch separate port8766 on loopback.
- [x] Mobile frontend: preserve reference logo/theme; camera, photo upload, review,
  correction and simulated receipt. Node regressions before implementation.
- [x] Vercel gateway: cookie integrity/expiry, route/method allowlist, body limit,
  fixed upstream/no redirects, timeouts/offline messages. Node regression tests first.
- [x] Network setup: official cloudflared binary, verified download provenance,
  token-protected tunnel and local process lifecycle helpers. No OS startup changes.
- [x] Deployment: verify team/project, create dedicated project, sensitive production
  env vars and source-only deployment. No training data or weights uploaded.
- [x] Verification: all Python/Node tests; real external HTTPS image->review->ACK
  flow; responsive browser checks; anonymous upstream denied; no secrets in assets.
- [x] Handoff: Conventional Commits, push branch, URL/access instructions and precise
  PC/tunnel restart limitations. Physical phone/camera test requires user's device.

## Review focus

Camera denial and HEIC; oversized photos; interrupted confirmation/retry; unknown
products falsely presented as certainty; unauthorized access to the PC; tunnel
URL churn; session expiry; serverless API routing and body parsing differences.

## Validation recorded

- Vercel deployment dpl_Ev6tYLuam9h8Jevin5S7sJR6e4Pe READY.
- Real HTTPS photo→review→ACK retry produced one simulated receipt line.
- Browser upload of supplied Colgate photo, correction/selection and confirmation passed; no console errors.
- Mobile layout measured 375px clientWidth/scrollWidth, no horizontal overflow.
- 138 Python tests +24 Node tests passed; one MySQL integration test skipped.
- Physical phone camera remains a user-device check, not claimed validated.
- Quick Tunnel restart URL requires Vercel BACKEND_URL update/redeploy; documented.
- Fresh independent review accepted PoC; default port fixed to8766 for consistent lifecycle helpers.
