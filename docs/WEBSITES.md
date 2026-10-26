# Websites in Genesis

Genesis builds **Android apps** (Kotlin/Compose APKs) and **simple websites** through the same conversation on
WhatsApp, SMS and the web chat. Both kinds share one project list, one build queue, one set of status and
cancel commands, and one notification path. Architecture and audit notes are in
[INTEGRATION_PLAN.md](../INTEGRATION_PLAN.md).

## What the website builder is

The website generator is not new code. It is the real `src/portfolio/` pipeline from
[adityapokuri229/weave](https://github.com/adityapokuri229/weave), run unmodified from a local checkout:

1. `researchDesignInspirations`: reads the minimal.gallery feed, then asks Gemini for a topic analysis and three
   design directions (fonts, palette, components).
2. `generateBespokeHtml`: Gemini writes one complete, responsive single-file HTML page (Tailwind CDN plus Google
   Fonts) for direction 1. Directions 2 and 3 are generated too when `GENESIS_WEBSITE_VARIANTS` is above 1.
3. `redesignBespokeHtml`: applies a change ("make the hero darker") to the current page.

Genesis runs these through `genesis/web/bridge.mjs` in a child process and adds:

| weave behaviour | What Genesis does instead |
|---|---|
| Loads `.env` with dotenv, reads stored Google OAuth tokens | `dotenv` resolves to a no-op stub. `HOME` and `WEAVE_DATA_DIR` point at an empty per-build sandbox. |
| Falls back to the `agy` CLI and to Antigravity Cloud Code OAuth | Blocked. Only the Gemini API key path runs. Without a key nothing is generated. |
| Returns a canned template, or the unchanged page, when Gemini fails | Detected. The build fails with the real error; it never "succeeds". |
| Always deploys to Netlify, falling back to anonymous Netlify Drop | Not used. Publishing is a separate, owner-approved step with no anonymous path. |
| Google Stitch screens, Firefox screenshots | Not integrated. Stitch needs `STITCH_API_KEY`, and screenshots need Firefox. |

Output is validated (`genesis/web/validate.py`): complete HTML, under 1 MB, scripts only from allowed HTTPS
CDNs, no iframes, `<base>`, meta refresh, or forms that post to other sites. Each version is kept in
`data/sites/<id>/site/`. A change writes a new version, so a failed change never touches the last good one.

## Setup

```bash
git clone https://github.com/adityapokuri229/weave.git ~/genesis-integration/weave-ref   # no npm install needed
```

In `.env`:

```
GENESIS_AI_BACKEND=api                     # the website engine uses the Gemini API key
GEMINI_API_KEY=...                         # already used for Android apps
GENESIS_WEBSITE_ENGINE_DIR=/Users/you/genesis-integration/weave-ref
```

Node.js 20 or later must be on `PATH` (or set `GENESIS_NODE_BIN`). Then run:

```bash
.venv/bin/python -m genesis doctor     # "Website builder" and "Website engine load" must be OK
```

The probe loads weave's modules without any AI call and prints the weave commit it found. This integration was
written and tested against commit `52fb655`. If weave changes the exported functions, the probe or the bridge
contract tests will report it.

## Using it

- "Create a premium website for my coffee brand" starts a website build.
- "Build an Android inventory app" starts an Android build.
- "Build something for my bakery" makes Genesis ask: "Android app or website?"
- "make the buttons bigger" changes the **active** project, whichever kind it is ("show my projects",
  "switch to 2").
- "send the link" sends a website's **private preview**: `/preview/<token>/`, expiring after
  `GENESIS_SMS_LINK_TTL_HOURS`, up to 200 page views.
- "what are you building?" or "how's it going?" reports the current job. It never starts one.

Previews are served from your Genesis server through the same tunnel as the APK links. The page is sent with a
CSP `sandbox` policy (no `allow-same-origin`), so generated scripts can't read Genesis cookies or call Genesis
APIs, can't send data anywhere (`connect-src 'none'`, `form-action 'none'`), and can load scripts and styles
only from the allowed CDNs. A preview is **not** a public deployment, and Genesis always says which one it sent.

## Publishing (optional, off by default)

```
GENESIS_WEBSITE_DEPLOY=netlify
NETLIFY_AUTH_TOKEN=...      # https://app.netlify.com/user/applications#personal-access-tokens
```

Even then:

1. Only an **owner** number can publish.
2. "publish it" (or `PUBLISH`) makes Genesis explain what will happen and ask for `PUBLISH`. "yes" is not
   enough, and anything else cancels.
3. The publish job uploads that exact version through the Netlify API (token in a header, never on a command
   line). The first publish creates a site named `genesis-<brand>-<random>`, and later publishes update the same site.
4. Genesis reports the real `https://….netlify.app` URL only after Netlify reports the deploy `ready`.
   Failures are reported, and the private preview keeps working.

Publishing has been tested only against a fake Netlify API. It has **not** been run against a real Netlify account.

## Limitations

- Websites are single static pages, with optional design options 2 and 3: no backend, logins, databases, payments
  or working forms.
- weave sends only the first 8,000 characters of the current page to Gemini when applying a change. Long pages can
  lose content in a change. Genesis records this in the build log.
- weave's design-research reply sometimes isn't valid JSON (2 of 3 real runs on 2026-10-21; one was before JSON mode
  was requested). weave then uses generic canned design directions. Genesis retries the research once, records
  `research: fallback` in the build record when it still fails, and names the site from the page title. The page
  itself is still written by Gemini.
- Real runs on this key took 2-4 minutes per Gemini call, so about 5 minutes for a new site and about 5.5 for a change.
- Website builds don't appear in the local dashboard's History. Their logs are in `data/sites/<id>/build.log`.
- One website build runs at a time, and each user has one job at a time across both kinds.
- Generated pages load Tailwind and Google Fonts from public CDNs when viewed.
