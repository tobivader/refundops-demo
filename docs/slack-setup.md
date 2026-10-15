# Slack: /refunds today

Implemented endpoint: `POST /slack/commands`. It verifies Slack's HMAC signature
over the original form body and rejects timestamps more than five minutes from
the server's clock. See [Slack request verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/).

## Connect the app

1. Open your RefundOps app at https://api.slack.com/apps.
2. Under Features → Slash Commands, click Create New Command.
3. Enter these settings:

| Setting | Value |
| --- | --- |
| Command | `/refunds` |
| Request URL | Your current ngrok HTTPS URL plus `/slack/commands` |
| Short Description | View refund statistics |
| Usage Hint | `today` |

4. Save. Under OAuth & Permissions, use Install to Workspace (or Reinstall if
   requested) and approve the command for your demo workspace. The slash command
   needs the `commands` permission. No chat history access is needed. We return
   the summary directly in the HTTP response, so no bot token is needed in Python.
5. In the terminal starting FastAPI, export the app's Signing Secret from Basic
   Information → App Credentials. Keep the existing database, Google, and GitHub
   settings too:

```bash
read -s -p 'Slack signing secret: ' SLACK_SIGNING_SECRET
export SLACK_SIGNING_SECRET
python -m uvicorn app.main:app --reload
```

Type the secret without quotes at the hidden prompt. Restarting Uvicorn is
necessary if its parent process did not previously have this environment setting.

6. Keep ngrok running. In your Slack channel, enter `/refunds today`.

The response includes Toronto's date, refund count, and amount. Values come from
PostgreSQL, not Sheets. The total assumes one demo currency and has no currency
symbol because no currency is stored in our records. Blank text, `help`, and
unsupported arguments return usage guidance.

## Response and error behavior

Replies use `response_type: ephemeral` so only the invoking person sees them.
Slack expects acknowledgement within three seconds; our simple read is given a
two-second processing budget. On timeout or database failure, the app returns a
friendly private response. The underlying worker-thread read may finish after
the HTTP response; this is not a durable background-job system.
See [Slack slash command documentation](https://docs.slack.dev/interactivity/implementing-slash-commands/).

Missing signing configuration returns 503; invalid signatures or stale timestamps
return 401. Ensure the machine clock is correct and use the Signing Secret,
not a bot token. Invalid forms or wrong command names return 422. If Slack
cannot connect, check ngrok, the route suffix, and FastAPI. Update Slack's Request
URL if the tunnel URL changes.

The endpoint and 61-test suite are verified locally with mocked database reads.
Actual Slack installation and live command response remain to be verified.
Only `today` is implemented; `count`, `total`, and analyst-specific commands
remain future work. Workspace-specific authorization beyond installation is not
implemented; this app is intended for the single demo workspace.
