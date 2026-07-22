import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    connection = psycopg.connect(
        get_database_url(),
        row_factory=dict_row,
        connect_timeout=10,
    )
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS agent_state_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            org_id TEXT,
            subscription_source TEXT,
            agent_id TEXT,
            agent_ci_user_id TEXT,
            task_id TEXT,
            queue_id TEXT,
            team_id TEXT,
            channel_id TEXT,
            channel_type TEXT,
            current_state TEXT,
            origin_value TEXT,
            destination_value TEXT,
            created_time_ms BIGINT,
            occurred_at TIMESTAMPTZ,
            received_at TIMESTAMPTZ NOT NULL,
            raw_payload JSONB NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_agent_state_events_agent_time
        ON agent_state_events (agent_id, occurred_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_agent_state_events_type_time
        ON agent_state_events (event_type, occurred_at DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS current_agent_states (
            agent_id TEXT NOT NULL,
            channel_type TEXT NOT NULL,
            agent_ci_user_id TEXT,
            task_id TEXT,
            queue_id TEXT,
            team_id TEXT,
            channel_id TEXT,
            current_state TEXT,
            origin_value TEXT,
            destination_value TEXT,
            state_started_at TIMESTAMPTZ,
            source_created_time_ms BIGINT,
            last_event_id TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (agent_id, channel_type)
        )
        """,
    ]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    logger.info("Database tables are ready")


def save_webhook_event(
    payload: dict[str, Any],
    received_at,
) -> bool:
    data = payload.get("data") or {}

    event_id = payload.get("id")
    event_type = (
        payload.get("eventType")
        or payload.get("event")
        or payload.get("type")
        or "unknown"
    )

    if not event_id:
        raise ValueError("Webhook payload does not contain an event id")

    created_time_ms = data.get("createdTime")
    agent_id = data.get("agentId")
    channel_type = data.get("channelType") or "unknown"

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_state_events (
                    event_id,
                    event_type,
                    org_id,
                    subscription_source,
                    agent_id,
                    agent_ci_user_id,
                    task_id,
                    queue_id,
                    team_id,
                    channel_id,
                    channel_type,
                    current_state,
                    origin_value,
                    destination_value,
                    created_time_ms,
                    occurred_at,
                    received_at,
                    raw_payload
                )
                VALUES (
                    %(event_id)s,
                    %(event_type)s,
                    %(org_id)s,
                    %(subscription_source)s,
                    %(agent_id)s,
                    %(agent_ci_user_id)s,
                    %(task_id)s,
                    %(queue_id)s,
                    %(team_id)s,
                    %(channel_id)s,
                    %(channel_type)s,
                    %(current_state)s,
                    %(origin_value)s,
                    %(destination_value)s,
                    %(created_time_ms)s,
                    CASE
                        WHEN %(created_time_ms)s IS NULL THEN NULL
                        ELSE TO_TIMESTAMP(%(created_time_ms)s / 1000.0)
                    END,
                    %(received_at)s,
                    %(raw_payload)s::jsonb
                )
                ON CONFLICT (event_id) DO NOTHING
                RETURNING event_id
                """,
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "org_id": payload.get("comciscoorgid"),
                    "subscription_source": payload.get("source"),
                    "agent_id": agent_id,
                    "agent_ci_user_id": data.get("agentCiUserId"),
                    "task_id": data.get("taskId"),
                    "queue_id": data.get("queueId"),
                    "team_id": data.get("teamId"),
                    "channel_id": data.get("channelId"),
                    "channel_type": channel_type,
                    "current_state": data.get("currentState"),
                    "origin_value": data.get("origin"),
                    "destination_value": data.get("destination"),
                    "created_time_ms": created_time_ms,
                    "received_at": received_at,
                    "raw_payload": json.dumps(payload),
                },
            )

            inserted = cursor.fetchone() is not None

            if agent_id and event_type in {
                "agent:login",
                "agent:logout",
                "agent:state_change",
                "agent:channel_state_change",
                "agent:channelType_state_change",
            }:
                cursor.execute(
                    """
                    INSERT INTO current_agent_states (
                        agent_id,
                        channel_type,
                        agent_ci_user_id,
                        task_id,
                        queue_id,
                        team_id,
                        channel_id,
                        current_state,
                        origin_value,
                        destination_value,
                        state_started_at,
                        source_created_time_ms,
                        last_event_id,
                        updated_at
                    )
                    VALUES (
                        %(agent_id)s,
                        %(channel_type)s,
                        %(agent_ci_user_id)s,
                        %(task_id)s,
                        %(queue_id)s,
                        %(team_id)s,
                        %(channel_id)s,
                        %(current_state)s,
                        %(origin_value)s,
                        %(destination_value)s,
                        CASE
                            WHEN %(created_time_ms)s IS NULL THEN %(received_at)s
                            ELSE TO_TIMESTAMP(%(created_time_ms)s / 1000.0)
                        END,
                        %(created_time_ms)s,
                        %(event_id)s,
                        NOW()
                    )
                    ON CONFLICT (agent_id, channel_type)
                    DO UPDATE SET
                        agent_ci_user_id = EXCLUDED.agent_ci_user_id,
                        task_id = EXCLUDED.task_id,
                        queue_id = EXCLUDED.queue_id,
                        team_id = EXCLUDED.team_id,
                        channel_id = EXCLUDED.channel_id,
                        current_state = EXCLUDED.current_state,
                        origin_value = EXCLUDED.origin_value,
                        destination_value = EXCLUDED.destination_value,
                        state_started_at = EXCLUDED.state_started_at,
                        source_created_time_ms = EXCLUDED.source_created_time_ms,
                        last_event_id = EXCLUDED.last_event_id,
                        updated_at = NOW()
                    WHERE current_agent_states.source_created_time_ms IS NULL
                       OR EXCLUDED.source_created_time_ms IS NULL
                       OR EXCLUDED.source_created_time_ms
                          >= current_agent_states.source_created_time_ms
                    """,
                    {
                        "agent_id": agent_id,
                        "channel_type": channel_type,
                        "agent_ci_user_id": data.get("agentCiUserId"),
                        "task_id": data.get("taskId"),
                        "queue_id": data.get("queueId"),
                        "team_id": data.get("teamId"),
                        "channel_id": data.get("channelId"),
                        "current_state": (
                            data.get("currentState")
                            or ("logged-in" if event_type == "agent:login" else None)
                            or ("logged-out" if event_type == "agent:logout" else None)
                        ),
                        "origin_value": data.get("origin"),
                        "destination_value": data.get("destination"),
                        "created_time_ms": created_time_ms,
                        "received_at": received_at,
                        "event_id": event_id,
                    },
                )

    return inserted


def list_recent_events(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    event_id,
                    event_type,
                    agent_id,
                    agent_ci_user_id,
                    task_id,
                    queue_id,
                    team_id,
                    channel_id,
                    channel_type,
                    current_state,
                    origin_value AS origin,
                    destination_value AS destination,
                    occurred_at,
                    received_at,
                    raw_payload
                FROM agent_state_events
                ORDER BY received_at DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            return list(cursor.fetchall())


def list_current_agent_states() -> list[dict[str, Any]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    agent_id,
                    channel_type,
                    agent_ci_user_id,
                    task_id,
                    queue_id,
                    team_id,
                    channel_id,
                    current_state,
                    origin_value AS origin,
                    destination_value AS destination,
                    state_started_at,
                    EXTRACT(
                        EPOCH FROM (NOW() - state_started_at)
                    )::BIGINT AS state_duration_seconds,
                    source_created_time_ms,
                    last_event_id,
                    updated_at
                FROM current_agent_states
                ORDER BY current_state, agent_id
                """
            )
            return list(cursor.fetchall())
