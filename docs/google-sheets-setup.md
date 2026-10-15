# Connect RefundOps to Google Sheets

The reporting code is implemented, but live Google access requires your local
credentials and a spreadsheet. Follow these steps once, then use the sync
command to verify the connection before testing automatic webhook updates.

## 1. Prepare a Google Cloud project

Open https://console.cloud.google.com/, select or create a project for RefundOps,
and enable **Google Sheets API** under APIs & Services → Library.
See [Google's API setup instructions](https://developers.google.com/workspace/guides/enable-apis).
The app does not use Gmail or require the Drive API for this workflow.

## 2. Create a service account and local key

Under IAM & Admin → Service Accounts, create a service account named
`refundops-reporter`. Project-wide Owner or Editor roles are unnecessary for
writing a spreadsheet shared directly with this account. Domain-wide delegation
is not required.

Open the account → Keys → Add key → Create new key → JSON. Save the downloaded
file privately. You may move it to `credentials/service-account.json` in the
project; `credentials/` is ignored by Git. Do not paste or upload the key into
chat. See [Google's credential instructions](https://developers.google.com/workspace/guides/create-credentials)
and [key creation steps](https://docs.cloud.google.com/iam/docs/keys-create-delete).

## 3. Create and share a dedicated demo spreadsheet

Create a spreadsheet named **RefundOps Reports**. Share it with the service
account email (shown on its Google Cloud page) as an **Editor**.

The application manages these worksheet columns:

| Worksheet | Managed range | Content |
| --- | --- | --- |
| Refund Log | A:G, all rows | Ticket, customer, amount, reason, analyst, date, status |
| Daily Summary | A:C, all rows | Toronto date, refund count, total amount |

The app creates those worksheets if missing. Every sync replaces their managed
values and clears stale rows. Keep manual data and formulas outside those
ranges, or on a separate worksheet. Existing formatting is preserved.

Copy the spreadsheet ID from its address:

```text
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
```

## 4. Configure and test in your terminal

Activate the virtual environment, then export the key's absolute path and ID:

```bash
source .venv/bin/activate
export GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/service-account.json"
export GOOGLE_SHEETS_SPREADSHEET_ID="your-spreadsheet-id"
python -m scripts.sync_sheets
```

Replace both placeholders with your own values. The sync command uses the same
PostgreSQL settings as the app and prompts for its password if needed. Expected:

```text
Synchronized Refund Log and Daily Summary from PostgreSQL.
```

Open the spreadsheet. For the single active October 9 refund, expect one log
row and a daily summary row containing `2026-10-09 | 1 | 29.99`. Summary dates
come from the refund source timestamps in America/Toronto, not the sync date.
Amounts and counts are written as literal text; totals are calculated precisely
in Python using Decimal rather than spreadsheet formulas.

## 5. Verify automatic updates

Start or restart FastAPI in the terminal with these Google settings, the webhook
secret, and exported PostgreSQL password. Keep ngrok running. Redeliver the
existing valid completion event to test reporting without creating a refund.

The webhook response now includes:

```json
{"status": "duplicate", "ticket_id": 1, "record_id": 1, "delivery_id": "...", "reporting_status": "synced"}
```

Create a new synthetic issue and label it completed to verify a second log row
and updated summary. Relabeling an already refunded ticket does not add a row.

## Failure and recovery behavior

| reporting_status | Meaning |
| --- | --- |
| disabled | Neither Google setting is configured; refund storage still works |
| synced | Both reporting worksheets were updated |
| failed | Reporting failed after refund processing; inspect logs and retry |

The refund commits before reporting. Sheets failure does not undo it, and the
webhook still returns 200 with `reporting_status: failed`. After fixing access,
run `python -m scripts.sync_sheets` or redeliver a valid completion event.
There is no background retry worker or durable sync-status table yet. You must
perform this recovery or trigger another sync to refresh the reports.

Both worksheets update in one atomic Sheets batch, including new worksheet
creation if needed. Full database snapshots make retries converge to one report
without duplicate appended rows. A PostgreSQL advisory lock serializes the
app's report writers while reading and publishing; manual sheet edits do not
use that lock. See [Google's batch update guide](https://developers.google.com/workspace/sheets/api/guides/batchupdate)
and [cell update examples](https://developers.google.com/workspace/sheets/api/samples/sheet).

This full refresh is intended for the small portfolio dataset. It holds a
database connection during Google writes and rewrites all report rows. Larger
datasets need a separate reporting job and an incremental strategy. All amounts
currently assume one demo currency.

If Google requests fail, check that Sheets API is enabled in the key's project,
the key is valid, the spreadsheet ID is correct, and the service account is an
Editor. A partially configured integration is reported as failed. Google error
payloads and credentials are not exposed in webhook responses or logs.
