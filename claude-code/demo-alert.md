Target-account demo-request alerts. Reads recent demo requests from the CRM, keeps target accounts, posts a short briefing per request to Slack.

Optional input: $ARGUMENTS

Note: the Python pipeline in this repo (`python -m demo_intel`) is the deterministic path and the one to schedule. This file shows the same flow as a Claude Code slash-command skill (save it as `.claude/commands/demo-alert.md`). It depends on a Salesforce MCP server and a Slack MCP server being connected, and it shells out to the repo's helpers for every decision that must be exact.

## Input parsing
- Empty: TEST mode. Post to the test DM, prefix messages with `:test_tube: *[TEST]*`.
- Contains `live`: LIVE mode. Post to the live channel.
- Contains `dry-run` or `preview`: print the drafted messages, post nothing.
- Contains a duration like `3d` or `since <date>`: use it instead of the default 2-day lookback.

## Config
- Test destination: `<SLACK_TEST_USER_ID>`. Live destination: `<SLACK_LIVE_CHANNEL_ID>`. Use ids, not name searches.
- Demo-request fields (examples, match your schema): `Demo_Request_Submitted__c`, `Demo_Request_Date__c`.
- Dedup state: `state/posted_ids.json`, managed only through the repo helpers. Never decide "already posted" by reading Slack history.

## Steps
1. Fetch. Query Contacts where the demo flag is true and the demo date is within the lookback (default 2 days). Select identity, title, account name and owner, LinkedIn, and the source / medium / campaign / term / landing page fields.
2. Filter. Pass each email to the repo's filter (`python -c` around `demo_intel.enrich.classify`, or just run `python -m demo_intel --dry-run`). Drop internal, freemail, and non-target domains. If nothing is left, stop and say nothing.
3. Dedup. Keep only record Ids not already in the state file. If none are new, stop quietly.
4. Enrich. For each remaining contact, query open Opportunities on the account (`IsClosed = false`) and recent campaign memberships for the contact.
5. Format. Top-level message: account (linked), tier, name, title, email in backticks, and a last line `ref:<record Id>`. Thread reply: LinkedIn, account owner, "How they got here" (only non-blank fields), recent activity, CRM links and open opportunities. Omit any section with no data. No advice, no commentary.
6. Post. Top-level first, then the detail as a thread reply under it. One thread per request.
7. Record. In LIVE mode only, after each successful post, add the record Id to the state file. Never in TEST or dry-run.

## Guardrails
- Read-only against the CRM. The only write is the Slack post (and the local state file).
- The model writes prose only. The pipeline decides what posts.
- If a CRM or Slack call fails, stop and report it. Do not fill in missing data.
