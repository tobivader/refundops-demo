# Rebuilding RefundOps: from an empty folder to our current app

This guide records what we built, why we built it, and how to rebuild it
yourself. It reflects the repository checked on October 10, 2026. It is a
learning companion; the README contains operational setup instructions.

## How to study

Create a separate practice folder. Work through one stage at a time. Read the
problem and exercise, write a first attempt, and then compare it with the named
files in this project. Run the check before moving on. Explain the result in
your own words rather than memorizing the code.

You do not need to rebuild the entire app in one sitting. Stop at a working
checkpoint. Do not create every folder at the beginning: add each folder when
you first need its responsibility.

## The problem we are solving

An analyst completes a refund in a support ticket and then manually copies its
details into reporting sheets. RefundOps is intended to automate that second
part. GitHub Issues simulates the ticket system. PostgreSQL stores the lasting
refund history. Google Sheets and Slack are planned reporting integrations.

Our app records completed refunds; it does not transfer money or process an
actual payment. The `refund-completed` label represents an analyst's completion
signal.

## Current checkpoint

| Feature | State |
| --- | --- |
| Basic JSON endpoint | Implemented |
| Refund schema and validation endpoint | Implemented |
| Signed GitHub webhook and event filtering | Implemented; live connection verified |
| Issue-body extraction | Implemented |
| PostgreSQL connection and refunds table | Implemented; live connection verified |
| Saving refunds | Implemented; live saved row verified |
| Delivery and ticket duplicate protection | Implemented; live duplicate response verified |
| GET /refunds | Implemented; live database read verified |
| Today's and analyst statistics | Implemented; live database check pending |
| Sheets refund log and daily summary | Implemented; credential setup and live verification pending |
| Slack /refunds today | Implemented; live workspace setup and verification pending |
| CSV import, deployment | Not implemented |

The current automated suite has 62 tests. Database-facing tests use mocks:
they verify Python orchestration and responses, not a real PostgreSQL server.
Manual checks supplied the live evidence above. A local ngrok tunnel is not
a deployed service.

## Folder map

```text
app/
  main.py                       Creates FastAPI and registers routers
  api/
    webhooks.py                 Receives events; returns HTTP responses
    refunds.py                  Reads saved refunds through HTTP
    stats.py                    Reads today's and analyst summaries
  core/config.py                Reads webhook configuration
  models/
    webhook.py                  Shape of incoming GitHub issue data
    refund.py                   RefundEvent and saved RefundRecord schemas
    stats.py                    Statistics response schemas
  services/
    github_service.py           Verifies signatures
    refund_service.py           Extracts, validates, and coordinates saving
  repositories/
    refund_repository.py        SQL INSERT and SELECT operations
  db/
    database.py                 Opens PostgreSQL connections
    schema.sql                  Defines the refunds table
    migrations/001_unique_ticket.sql   Upgrades the older table safely
scripts/
  check_database.py             Checks the connection
  init_database.py              Creates the table
  migrate_unique_ticket.py      Archives old duplicate tickets; adds uniqueness
tests/                          Automated checks outside runtime app code
```

`__init__.py` marks a directory as a Python package. Our `app.main:app` server
command means “import the object named app from the module app.main.”

Pydantic models describe and validate application data. The SQL schema describes
database storage. We use direct SQL with Psycopg rather than an ORM, so this
project currently has no `app/db/models.py`.

## Stage 1: receive an HTTP request

**Problem:** Before connecting GitHub, prove our server can receive JSON.

**Concept:** A client sends a request to a server. A route handles an HTTP
method and path. A POST body contains the submitted data. FastAPI turns the
returned Python dictionary into a JSON response. Uvicorn runs the server.

**Files:** `app/main.py`, `app/api/webhooks.py`, `requirements.txt`, `.gitignore`.

**Exercise:** In your practice folder, create a FastAPI application and
`POST /webhooks/test`. Accept a JSON object and return `{"received": true}`.
Put the route in an `APIRouter` and register it in `main.py`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Use dependencies appropriate to the stage; our current requirements include
later database dependencies too.

**Check:** Open http://127.0.0.1:8000/docs or send:

```bash
curl -i -X POST http://127.0.0.1:8000/webhooks/test \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id": 1}'
```

A JSON object returns 200; a missing body or an array returns 422.

**Explain:** Who is the client? Where does the JSON live? Why does registering
a router matter? This manual request is a simulation; a webhook is a request
another system automatically sends when an event happens. Polling repeatedly
asks that system whether something changed.

## Stage 2: define valid refund data

**Problem:** Accepting arbitrary JSON does not establish that it is a refund.

**Concept:** A schema lists fields, types, and rules. Pydantic validates input
and produces a structured object. Type annotations tell FastAPI which schema
to use before running a route.

**Files:** `app/models/refund.py`, the `/webhooks/test/refund` route,
`tests/test_refund_model.py`.

**Exercise:** Build `RefundEvent` with `ticket_id`, `customer_id`,
`refund_amount`, `refund_reason`, `analyst`, `refund_date`, and `status`.
Require a positive strict integer ticket ID, nonblank text, a positive amount
with at most two decimal places and twelve total digits, a timezone-aware date,
and the literal status `completed`. Reject unexpected fields.

`Decimal` keeps monetary arithmetic precise. `AwareDatetime` requires timezone
information. `Literal["completed"]` allows that specific value. All fields
are required here because we have not given them defaults.

**Check:** Submit a valid refund to `/webhooks/test/refund`. Then try a negative
amount, missing analyst, blank reason, three decimal places, and `pending`.
Invalid data should return 422. This endpoint validates and echoes; it never saves.

**Explain:** Why is a dictionary of arbitrary JSON insufficient? Why is money
returned as a string such as `"29.99"`? It preserves decimal precision in JSON.

## Stage 3: use GitHub as the fake CRM

**Problem:** We need a ticket interface and a real event sender.

**Files:** This stage is repository configuration, not Python source.

**Exercise:** Create a demo repository and labels `billing`, `refund-requested`,
`refund-approved`, and `refund-completed`. Create a synthetic support issue:

```text
Customer ID: CUST-1842
Refund Amount: 29.99
Refund Reason: Service outage
Analyst: analyst_07
```

**Check:** Use the gear beside Labels to apply a label. Labeling changes the
issue; it does not require editing the description or closing the issue.

**Explain:** The issue number is our ticket ID. `CUST-1842` is a customer ID,
so issue #1 and customer CUST-1842 can correctly appear together.

## Stage 4: receive a signed GitHub webhook

**Problem:** GitHub needs to reach the server, and the server must verify the
request before trusting its contents.

**Files:** `core/config.py`, `services/github_service.py`, `models/webhook.py`,
`api/webhooks.py`, `.env.example`, and `tests/test_webhooks.py`.

**Exercise:** Build `/webhooks/github`. Read the original body bytes, calculate
HMAC-SHA256 with the shared secret, and compare using `hmac.compare_digest`.
The expected signature is prefixed with `sha256=`. Verify before parsing JSON.

Read `X-GitHub-Event` and `X-GitHub-Delivery`. For issue events, validate
`action`, `issue`, and `label`. Only continue for `action=labeled` and
`label.name=refund-completed`. Ignore pull request events and unrelated actions.
The GitHub schema allows extra fields because GitHub sends more data than we need.

Configure `GITHUB_WEBHOOK_SECRET` in the terminal running Uvicorn. Expose
port 8000 with ngrok. Set GitHub's payload URL to the tunnel's HTTPS address
plus `/webhooks/github`, content type to `application/json`, the same secret,
and event subscription to **Issues**. Leave both processes running.

The ngrok account token and the GitHub webhook secret serve different purposes.
Enter both privately. `.env.example` only documents variables; our app does not
load it or a `.env` file automatically. Exported variables belong to a terminal
process and its children; a new terminal does not inherit another's exports.

**Check:** Apply the completion label and inspect GitHub Settings → Webhooks →
your webhook → Recent Deliveries → Response. In this historical stage the
response was `detected`. The current implementation returns `saved` or `duplicate`.

| HTTP status | Meaning in our GitHub endpoint |
| --- | --- |
| 200 | Saved, duplicate, or ignored; inspect the JSON body |
| 400 | Missing event or delivery header |
| 401 | Invalid or missing signature |
| 422 | Invalid issue payload or refund details |
| 503 | Missing webhook secret or failed database operation |

**Explain:** Why must we sign the original bytes rather than reconstructed JSON?
Why cannot GitHub use your computer's localhost address? Why would subscribing
only to Pushes fail to notify us about a label change?

## Stage 5: extract refund details in a service

**Problem:** The issue body is text; our application needs validated fields.

**Files:** `services/refund_service.py`, `tests/test_refund_service.py`.

**Exercise:** Split the body into lines. Use `partition(":")` to split each
line at its first colon. Normalize the label with `strip().lower()`, map known
labels to internal field names, and trim values. Ignore unknown lines, reject
duplicate known fields, detect missing fields, then construct `RefundEvent`.

Example transformation:

```text
Refund Amount: 29.99 → field refund_amount → Decimal("29.99")
```

Use the issue number for the ticket ID, `updated_at` for the source refund date,
and `completed` for status. The timestamp is the source update time, not a
payment provider's settlement time. Reusing it keeps identical payloads stable.

`InvalidRefundError` represents an application error. The service raises it;
the API catches it and turns it into HTTP 422. This keeps HTTP details out of
the service. Missing text is checked by extraction; invalid values are checked
by Pydantic. Duplicate recognized lines are rejected to avoid guessing a value.

**Check:** Remove the analyst line, save the issue, and remove/reapply the
completion label. Expect `Missing refund fields: analyst`. Restore the line
and repeat. Use plain-text fields without bold formatting or currency symbols.

**Explain:** A service is a responsibility, not a Python language feature.
We put the logic in a class to group related operations. A function was enough
initially; the class now also holds a repository supplied through `__init__`.
`self.repository` lets its methods use that dependency. Tests can supply a fake.

## Stage 6: connect to PostgreSQL

**Problem:** An acknowledged request does not give us lasting refund history.

**Files:** `db/database.py`, `scripts/check_database.py`, database requirements.

**Concept:** PostgreSQL is the database server; pgAdmin is a management interface.
A pgAdmin server name such as PostgreSQL Local is a display label. `refundops`
is a database inside the server. A table contains rows (records) and columns.

**Exercise:** Create `refundops` using pgAdmin's Databases → Create → Database.
Use Psycopg to connect with host `localhost`, port `5432`, database `refundops`,
and user `postgres` for the local setup. Read configuration from the environment.
Use a short connection timeout and keep the password out of source code.

```bash
python -m scripts.check_database
```

**Check:** Enter the password at the hidden prompt and expect:
`Connected successfully: database=refundops, user=postgres`.

**Explain:** A connection is the channel to PostgreSQL; a cursor sends SQL and
reads results. `SELECT current_database(), current_user` checks the destination.
The check command's password is used only for that process, not saved for FastAPI.

## Stage 7: define storage and save through a repository

**Problem:** We need a lasting row for each completed refund.

**Files:** `db/schema.sql`, `scripts/init_database.py`,
`repositories/refund_repository.py`, `services/refund_service.py`.

**Exercise:** Define the table, run `python -m scripts.init_database`, then
build a repository `save()` method using parameterized INSERT and RETURNING.
Use the refund fields plus `id`, `github_delivery_id`, and `created_at`.

| SQL concept | Why we use it |
| --- | --- |
| Primary key and identity | Automatically identify each row |
| NUMERIC(12,2) | Store an exact decimal amount |
| TIMESTAMPTZ | Store a timezone-aware instant |
| NOT NULL | Require a value |
| CHECK | Enforce value rules in the database |
| UNIQUE | Prevent conflicting delivery or ticket records |

The current schema includes ticket uniqueness added in Stage 8. On an existing
table, `CREATE TABLE IF NOT EXISTS` skips creation; it does not modify columns
or add new constraints. That is why we need migrations.

A repository here is Python database-access code, not a GitHub repository.
`RefundService.process_refund()` first calls `extract_refund()`, then
`self.repository.save(refund, delivery_id)`. The repository owns the SQL.

`%s` placeholders and a separate parameter tuple pass values safely without
turning ticket text into SQL. The connection's `with` block commits on success
and rolls back on failure. We return success after the block completes.
The async webhook route runs synchronous database work in a worker thread.

**Check:** Give FastAPI its database password in its terminal, using bash:

```bash
read -s -p 'PostgreSQL password: ' PGPASSWORD
export PGPASSWORD
python -m uvicorn app.main:app --reload
```

Type the password after the prompt; `-p` is the prompt text, not the password.
Keep the webhook secret configured too. Trigger the label and expect `saved`.
In pgAdmin's Query Tool for refundops, run `SELECT * FROM public.refunds;`.

**Explain:** Saving makes history survive application restarts, supports totals,
and gives future reporting integrations a source of truth.

## Stage 8: prevent duplicate deliveries and duplicate tickets

**Problem:** A repeated request or repeated completion label must not count the
same refund twice.

**Files:** Repository `save()`, unique constraints, migration SQL and command,
repository and webhook tests.

**Exercise:** First distinguish these cases:

| Action | Delivery ID | Rule |
| --- | --- | --- |
| Redeliver the same event | Same ID | Do not save again |
| Remove/reapply the label | New ID, same ticket | Do not save again |
| Complete another issue | New ID and ticket | Save a new refund |

Enforce both rules in PostgreSQL. `ON CONFLICT DO NOTHING` handles uniqueness
conflicts; if INSERT returns no row, retrieve the existing record by delivery
ID or ticket ID. `SaveResult` holds `record_id`, `ticket_id`, and `created`.
The route chooses `saved` or `duplicate` using that result.

Originally we enforced delivery uniqueness only and saw two rows for ticket 1.
We then chose the business rule **one refund per ticket**. The migration keeps
the earliest saved row and preserves later rows in `refunds_duplicate_archive`.
It locks the table, archives duplicates, and adds the constraint within one
transaction. A failure rolls everything back.

For an older database, run:

```bash
python -m scripts.migrate_unique_ticket
```

Fresh databases created with the current schema already have ticket uniqueness.
This design currently assumes one source repository: issue numbers alone would
not identify tickets uniquely across multiple repositories.

**Check:** Redeliver and also relabel the same issue. Both should return
`duplicate` and leave one active row. Query the archive to inspect preserved
historical copies. Later attempts do not overwrite the original refund.

**Explain:** The webhook response `duplicate` describes request handling;
the stored refund's `completed` describes its business state. Identity values
can have gaps because attempted inserts can consume a sequence value.

## Stage 9: read refunds through HTTP

**Problem:** View saved records without opening pgAdmin.

**Files:** `api/refunds.py`, `RefundRecord` in `models/refund.py`, repository
`list_refunds()`, `main.py`, `tests/test_refunds_api.py`.

**Exercise:** Add a parameterized SELECT ordered by `id DESC`. Support `limit`
and `offset`. Convert dictionary rows into `RefundRecord`, which extends
`RefundEvent` with database ID, delivery ID, and creation timestamp.
Register a GET /refunds router in `main.py`.

This simple read needs no extra business service. A synchronous FastAPI route
runs in a worker thread. Query validation requires limit 1–100 and offset ≥ 0;
defaults are 50 and 0. Database failures become 503 without exposing raw errors.

**Check:** Open http://127.0.0.1:8000/refunds and compare with pgAdmin. Try
`/refunds?limit=10&offset=0` and an invalid limit. No rows should return `[]`.

**Explain:** The outer JSON array is the list of refunds; each object is a row.
`id` identifies the database record, `ticket_id` identifies the support issue,
and `created_at` is when the row was saved. Offset pages can shift as new
records arrive. The current read endpoint has no authentication and is intended
for synthetic demo data.

## Stage 10: today's and analyst statistics

Implemented files are `models/stats.py`, `api/stats.py`, repository methods
`get_today_stats()` and `get_analyst_stats()`, and `tests/test_stats.py`.

**Problem:** Count today's refunds and total their amounts in America/Toronto.

**Exercise:** Add `get_today_stats()` inside `RefundRepository`. Reuse the
connection and dictionary-cursor pattern. Our first discussed query was:

```sql
SELECT
    COUNT(*) AS refund_count,
    COALESCE(SUM(refund_amount), 0) AS total_refunded
FROM public.refunds
WHERE (refund_date AT TIME ZONE 'America/Toronto')::date
    = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Toronto')::date;
```

`COUNT(*)` counts matching rows, `SUM` totals amounts, and `COALESCE` supplies
zero when SUM has no input. `AS` names a result column. `AT TIME ZONE` converts
the instant to Toronto local time; `::date` takes its date. The query uses the
database server's clock. A refund dated October 9 should not count on October 10.

The implemented version instead calculates Toronto's date from the application's
timezone-aware clock, then constructs local midnight and the next local
midnight. It converts both to UTC and uses parameterized SQL:

```sql
WHERE refund_date >= %s AND refund_date < %s
```

The start is included and the end excluded. This avoids applying a conversion
to every refund row and supports days with 23 or 25 hours during daylight-saving
changes. `today_window()` accepts a supplied clock for deterministic tests.

`TodayStats` extends count and Decimal total with the local date and timezone.
`AnalystStats` adds the analyst name. The all-time analyst query uses
`GROUP BY analyst` to calculate one summary for each analyst, ordered by name.
Totals assume the demo's amounts share a currency; currency conversion is not
implemented.

**Check:** Open `/stats/today` and `/stats/analysts` on the local server. Today
returns zero if no refund's source date falls within today's Toronto date.
An empty analyst dataset returns `[]`. A new refund must use a new issue:
relabeling an existing refunded ticket is a duplicate and will not affect totals.

**Explain:** Why can UTC's date differ from Toronto's date? Why is next midnight
excluded? What is the difference between today's totals and all-time analyst
totals? The models define response shapes, the API handles HTTP, and the
repository performs aggregation; another service is unnecessary for this read.

**Next:** Verify these summaries against live PostgreSQL, then begin Google
Sheets reporting.

## Stage 11: publish Google Sheets reports

**Problem:** Operations needs a refund log and daily summary without manual
copying. PostgreSQL remains the source of truth; Sheets is a reporting view.

**Files:** `services/sheets_service.py`, repository `reporting_snapshot()`,
the webhook's reporting call, `scripts/sync_sheets.py`, and `tests/test_sheets_service.py`.
Follow [the live setup guide](google-sheets-setup.md) for account configuration.

**Exercise:** First implement the pure `build_report_rows(records)` function.
Build one log row per refund; group by Toronto source date and sum Decimal
amounts to build the summary. Test an empty database and exact totals such as
0.10 + 0.20 = 0.30. This calculation needs no Google credentials.

Then add authenticated Google requests. A service account is the application's
Google identity; the shared spreadsheet grants it editing access. The key is
private local configuration, not business data. AuthorizedSession obtains
access tokens and sends authenticated requests using the Sheets-only scope.

Read worksheet metadata and issue one batch containing missing-sheet creation,
grid expansion if needed, and both value updates. Use stringValue for literal
text, including amounts, so ticket text cannot be interpreted as a formula.
The app owns log columns A:G and summary columns A:C. Unbounded row ranges
clear stale trailing values. Full snapshots keep retries idempotent without
appending duplicate rows.

The repository acquires an advisory lock before reading one snapshot and keeps
it through the Sheets write. This prevents the app's concurrent refreshes from
overwriting newer reports with older ones. The database refund insert has
already committed, so reporting failure never removes a saved refund.

**Check:** Run `python -m scripts.sync_sheets`, verify both worksheets, repeat
and confirm unchanged row counts. Redeliver a webhook and check reporting_status.
This live verification remains pending; tests mock the Google requests.

**Explain:** Why not append on every retry? Why keep PostgreSQL as the source
of truth? Why does a duplicate completion still trigger reporting? It can repair
a failed previous sync. Why isn't this a production-scale reporting worker?
It refreshes all rows synchronously and has manual, rather than scheduled, retry.

## Testing and debugging as you rebuild

### Slack checkpoint added October 15

`app/api/slack.py` receives signed URL-encoded slash command requests.
`app/services/slack_service.py` verifies signatures and builds the response.
The service calls the existing `get_today_stats()` method, reusing our reporting
logic. No Sheets scraping, new database, or bot token is required.

Rebuild exercise: verify the `v0:timestamp:body` signature, reject timestamps
outside five minutes, parse command and text only after verification, and return
today's count and total as an ephemeral response. Unlike GitHub's JSON webhook,
Slack sends form data and requires an acknowledgement within three seconds.
Test modified bodies, old timestamps, zero refunds, database failures, and slow
reads. We bound processing at two seconds and return a friendly failure message.
See [the Slack setup guide](slack-setup.md) for the manual live check. Other
planned command arguments are not implemented yet.

Keep observed incidents in [the debugging notes](debugging-notes.md). The
October 15 entry explains a missing webhook secret that caused HTTP 503,
the successful recovery reported by the user, and why exporting a setting
before starting Uvicorn matters. Automatic reporting verification remains separate.

Run the current suite from the project root:

```bash
python -m unittest discover -v
```

| Test file | What it checks |
| --- | --- |
| test_refund_model.py | Required fields, amounts, text, statuses, timestamps |
| test_refund_service.py | Extraction and calling storage only for valid refunds |
| test_webhooks.py | Signed requests, filtering, saving, duplicate/error responses |
| test_refund_repository.py | Insert/conflict result handling using mocked cursors |
| test_refunds_api.py | Read responses, pagination, database failure handling |
| test_stats.py | Toronto date boundaries, daylight saving, decimal totals, HTTP responses |
| test_sheets_service.py | Exact report totals, request batches, literal values, snapshot locking, failures |

ASGI test helpers send requests directly into FastAPI without a network server.
Mocks replace external dependencies with controlled results. They do not prove
that SQL executes successfully in PostgreSQL; retain real database checks.

When stuck, locate the first failing step: did GitHub send a delivery, did ngrok
forward it, did signature validation pass, did extraction pass, did SQL succeed?
Look at Recent Deliveries, FastAPI logs, and the database rather than guessing.

## Explain the complete current flow

```text
Analyst labels a GitHub issue
  → GitHub sends a signed POST
  → ngrok forwards it to FastAPI
  → API verifies and filters the event
  → RefundService extracts and validates details
  → RefundRepository attempts an INSERT
  → PostgreSQL enforces uniqueness and commits
  → API returns saved or duplicate

Browser GET /refunds
  → API asks the repository for rows
  → PostgreSQL returns records
  → RefundRecord validates the response shape
  → FastAPI sends JSON
```

Try explaining why each folder exists and tracing one valid refund, one missing
analyst, one duplicate, and one database failure. If you can explain those paths,
you understand the current application better than memorizing its filenames.

## Future chapters to add as we build

Verify Google Sheets live access, then add Slack commands,
small CSV import, more failure handling, and deployment only after each is built
and verified. Ticket simulation can automate creating and labeling real GitHub
Issues; the script is the driver, and Issues are the simulated CRM.

Keep a payment simulator or a second service as a future extension. The current
scope is one explainable backend with PostgreSQL and reporting integrations.
