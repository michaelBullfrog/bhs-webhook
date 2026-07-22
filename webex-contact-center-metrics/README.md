# Webex Contact Center Metrics

FastAPI service for collecting near-real-time Webex Contact Center
agent events and preparing the data for PostgreSQL and Power BI.

## Current endpoints

- `GET /`
- `GET /health`
- `GET /api/webex/contact-center/webhook`
- `POST /api/webex/contact-center/webhook`
- `GET /docs`

## Architecture

Webex Contact Center webhooks → FastAPI → PostgreSQL → Power BI

## Local setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and enter local values.
4. Start the application:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Open:

   ```text
   http://127.0.0.1:8000/docs
   ```

## Render deployment

Create a new Render Blueprint and select this GitHub repository.
Render will read `render.yaml`.

Enter these environment variables in Render when prompted:

- `WEBEX_CLIENT_ID`
- `WEBEX_CLIENT_SECRET`
- `WEBEX_SERVICE_APP_ID`
- `WEBEX_ACCESS_TOKEN`
- `WEBEX_REFRESH_TOKEN`
- `DATABASE_URL` when PostgreSQL is added

Never commit real credentials, tokens, or `.env` files to GitHub.

## Webhook test

Send a POST request to:

```text
/api/webex/contact-center/webhook
```

Example JSON:

```json
{
  "eventType": "agent:channel_state_change",
  "agentId": "test-agent-123",
  "channelType": "telephony",
  "state": "available",
  "createdTime": 1784750400000
}
```

The service should return HTTP `202 Accepted`.
