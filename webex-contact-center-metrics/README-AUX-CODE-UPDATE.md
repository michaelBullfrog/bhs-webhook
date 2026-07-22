# Auxiliary-code lookup update

Replace or add:

- `app/database.py`
- `app/webex_lookups.py`
- `app/webhook_routes.py`
- `app/main.py`

Add these Render environment variables:

- `WEBEX_ORG_ID`
- `WEBEX_CC_API_BASE_URL`

Existing variables still required:

- `WEBEX_ACCESS_TOKEN`
- `DATABASE_URL`

After deployment, run:

`POST /api/webex/contact-center/lookups/auxiliary-codes/sync`

Then inspect:

- `GET /api/webex/contact-center/lookups/auxiliary-codes`
- `GET /api/webex/contact-center/events`
- `GET /api/webex/contact-center/agents/current`

The sync pulls both IDLE_CODE and WRAP_UP_CODE values from Webex and stores their real configured names.
