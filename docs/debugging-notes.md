# RefundOps debugging notes

## October 15, 2026: GitHub webhook returns HTTP 503

### Observation

After restarting FastAPI during Google Sheets setup, GitHub webhook requests
reached Uvicorn but returned HTTP 503. FastAPI startup completed normally.
GitHub's delivery response body was:

```json
{"detail":"GitHub webhook secret is not configured"}
```

The standalone Sheets synchronization had already succeeded. That confirmed
the sync command could access PostgreSQL and Google Sheets, but it did not
prove the FastAPI process had every webhook setting.

### Diagnosis

`app/api/webhooks.py` calls `get_github_webhook_secret()` before verifying the
signature. `app/core/config.py` reads `GITHUB_WEBHOOK_SECRET` from the process
environment. If it is missing or empty, the route deliberately returns 503.

The evidence establishes that this setting was absent or empty in the server
process. A likely cause is starting Uvicorn from a terminal where the secret
was not exported. We have not independently confirmed that terminal history.
Environment exports in one terminal do not configure another terminal, and
the current application does not automatically load `.env` files.

This was not evidence of a Sheets outage, invalid signature, or failed INSERT:
the route exited before those operations. A server can start successfully
while a particular endpoint remains unconfigured.

### Corrective action

Stop Uvicorn with Ctrl+C. In the same terminal that will launch it, export the
same webhook secret configured in GitHub. Do not generate a different secret
unless intentionally updating both ends.

To avoid placing the value directly in command history, use bash:

```bash
read -s -p 'GitHub webhook secret: ' GITHUB_WEBHOOK_SECRET
export GITHUB_WEBHOOK_SECRET
python -m uvicorn app.main:app --reload
```

Enter the existing secret at the hidden prompt, then press Enter. Keep the
PostgreSQL and Google settings configured in that same terminal as well.
The ngrok account token, PostgreSQL password, and webhook secret are distinct.

### Verification — recovery reported successful

The user confirmed that entering the existing secret, exporting it, and
restarting FastAPI resolved the webhook error on October 15, 2026. No secret
rotation was performed. Exact response JSON and post-recovery spreadsheet
contents were not supplied, so automatic Sheets synchronization still needs
an explicit end-to-end check.

Remaining verification:

Redeliver the failed valid `issues.labeled` completion event in GitHub.
Expected for an already saved ticket:

```json
{"status":"duplicate","ticket_id":1,"record_id":1,"delivery_id":"...","reporting_status":"synced"}
```

Confirm HTTP 200, reporting_status synced, one active database refund, and
unchanged spreadsheet row counts for a duplicate event.

### What the fix did, in plain language

GitHub uses the shared secret to sign a webhook body. FastAPI uses the same
secret to verify the signature. GitHub had its copy, but the running server
could not read its copy from the environment.

`read -s` collected the secret without displaying typing; `-p` specified the
prompt text. The user entered the value without quotation marks. `export`
made the variable available to programs launched from that terminal. Starting
Uvicorn there let the server inherit it. The setting was restored; refund data
and the shared secret itself were not changed. A new terminal needs configuration
again because this app currently does not automatically load an environment file.

### Interview talking point

“While connecting Sheets reporting, I encountered a 503 on a GitHub webhook.
I inspected the delivery response rather than assuming the tunnel or database
was broken. It identified missing webhook-secret configuration. I traced that
to the server's environment lookup. Exporting the existing secret in the terminal
launching Uvicorn and restarting it restored webhook processing. The endpoint
refused to process unverifiable requests rather than bypassing verification.
The lesson was that a running server can still lack required configuration.”

### Improvement to consider

Validate required production configuration at startup so missing settings are
detected earlier. Keep secret values out of logs; expose useful error categories
and document which environment variables each process needs. This improvement
is proposed, not implemented by this documentation change.
