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
        CREATE TABLE IF NOT EXISTS auxiliary_codes (
            auxiliary_code_id TEXT PRIMARY KEY,
            code_name TEXT NOT NULL,
            code_type TEXT NOT NULL,
            is_system BOOLEAN,
            is_default BOOLEAN,
            active BOOLEAN DEFAULT TRUE,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            raw_payload JSONB
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS contact_center_users (
            user_id TEXT PRIMARY KEY,
            ci_user_id TEXT,
            first_name TEXT,
            last_name TEXT,
            display_name TEXT,
            email TEXT,
            site_id TEXT,
            primary_team_id TEXT,
            team_ids JSONB,
            contact_center_enabled BOOLEAN,
            active BOOLEAN,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            raw_payload JSONB
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_contact_center_users_ci_user_id
        ON contact_center_users (ci_user_id)
        WHERE ci_user_id IS NOT NULL
        """,
        """
        ALTER TABLE contact_center_users
        ADD COLUMN IF NOT EXISTS primary_team_id TEXT
        """,
        """
        ALTER TABLE contact_center_users
        ADD COLUMN IF NOT EXISTS team_ids JSONB
        """,
        """
        CREATE TABLE IF NOT EXISTS contact_center_teams (
            team_id TEXT PRIMARY KEY,
            team_name TEXT NOT NULL,
            team_type TEXT,
            team_status TEXT,
            site_id TEXT,
            site_name TEXT,
            active BOOLEAN,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            raw_payload JSONB
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS contact_center_queues (
            queue_id TEXT PRIMARY KEY,
            queue_name TEXT NOT NULL,
            queue_type TEXT,
            channel_type TEXT,
            routing_type TEXT,
            active BOOLEAN,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            raw_payload JSONB
        )
        """,
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
            idle_code_id TEXT,
            idle_code_name TEXT,
            wrapup_code_id TEXT,
            wrapup_code_name TEXT,
            origin_value TEXT,
            destination_value TEXT,
            created_time_ms BIGINT,
            occurred_at TIMESTAMPTZ,
            received_at TIMESTAMPTZ NOT NULL,
            raw_payload JSONB NOT NULL
        )
        """,
        """
        ALTER TABLE agent_state_events
        ADD COLUMN IF NOT EXISTS idle_code_id TEXT
        """,
        """
        ALTER TABLE agent_state_events
        ADD COLUMN IF NOT EXISTS idle_code_name TEXT
        """,
        """
        ALTER TABLE agent_state_events
        ADD COLUMN IF NOT EXISTS wrapup_code_id TEXT
        """,
        """
        ALTER TABLE agent_state_events
        ADD COLUMN IF NOT EXISTS wrapup_code_name TEXT
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
            idle_code_id TEXT,
            idle_code_name TEXT,
            wrapup_code_id TEXT,
            wrapup_code_name TEXT,
            origin_value TEXT,
            destination_value TEXT,
            state_started_at TIMESTAMPTZ,
            source_created_time_ms BIGINT,
            last_event_id TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (agent_id, channel_type)
        )
        """,
        """
        ALTER TABLE current_agent_states
        ADD COLUMN IF NOT EXISTS idle_code_id TEXT
        """,
        """
        ALTER TABLE current_agent_states
        ADD COLUMN IF NOT EXISTS idle_code_name TEXT
        """,
        """
        ALTER TABLE current_agent_states
        ADD COLUMN IF NOT EXISTS wrapup_code_id TEXT
        """,
        """
        ALTER TABLE current_agent_states
        ADD COLUMN IF NOT EXISTS wrapup_code_name TEXT
        """,
    ]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    logger.info("Database tables and migrations are ready")


def lookup_auxiliary_code_name(code_id: str | None) -> str | None:
    if not code_id:
        return None

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT code_name
                FROM auxiliary_codes
                WHERE auxiliary_code_id = %s
                """,
                (code_id,),
            )
            row = cursor.fetchone()
            return row["code_name"] if row else None


def upsert_auxiliary_codes(
    codes: list[dict[str, Any]],
    code_type: str,
) -> int:
    count = 0

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for code in codes:
                code_id = code.get("id")
                code_name = code.get("name")

                if not code_id or not code_name:
                    continue

                cursor.execute(
                    """
                    INSERT INTO auxiliary_codes (
                        auxiliary_code_id,
                        code_name,
                        code_type,
                        is_system,
                        is_default,
                        active,
                        synced_at,
                        raw_payload
                    )
                    VALUES (
                        %(code_id)s,
                        %(code_name)s,
                        %(code_type)s,
                        %(is_system)s,
                        %(is_default)s,
                        %(active)s,
                        NOW(),
                        %(raw_payload)s::jsonb
                    )
                    ON CONFLICT (auxiliary_code_id)
                    DO UPDATE SET
                        code_name = EXCLUDED.code_name,
                        code_type = EXCLUDED.code_type,
                        is_system = EXCLUDED.is_system,
                        is_default = EXCLUDED.is_default,
                        active = EXCLUDED.active,
                        synced_at = NOW(),
                        raw_payload = EXCLUDED.raw_payload
                    """,
                    {
                        "code_id": code_id,
                        "code_name": code_name,
                        "code_type": code_type,
                        "is_system": (
                            code.get("isSystem")
                            if "isSystem" in code
                            else code.get("isSystemCode")
                        ),
                        "is_default": (
                            code.get("isDefault")
                            if "isDefault" in code
                            else code.get("defaultCode")
                        ),
                        "active": code.get("active", True),
                        "raw_payload": json.dumps(code),
                    },
                )
                count += 1

    return count


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

    idle_code_id = (
        data.get("idleCodeId")
        or data.get("auxCodeId")
        or data.get("idleCode")
    )
    idle_code_name = data.get("idleCodeName")

    wrapup_code_id = (
        data.get("wrapUpAuxCodeId")
        or data.get("wrapupAuxCodeId")
        or data.get("wrapUpCodeId")
        or data.get("wrapupCodeId")
        or data.get("auxCodeId")
        if str(data.get("currentState", "")).lower() == "wrapup"
        else (
            data.get("wrapUpAuxCodeId")
            or data.get("wrapupAuxCodeId")
            or data.get("wrapUpCodeId")
            or data.get("wrapupCodeId")
        )
    )
    wrapup_code_name = (
        data.get("wrapUpCodeName")
        or data.get("wrapupCodeName")
        or data.get("wrapUpReason")
        or data.get("wrapupReason")
    )

    if idle_code_id and not idle_code_name:
        idle_code_name = lookup_auxiliary_code_name(idle_code_id)

    if wrapup_code_id and not wrapup_code_name:
        wrapup_code_name = lookup_auxiliary_code_name(wrapup_code_id)

    parameters = {
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
        "idle_code_id": idle_code_id,
        "idle_code_name": idle_code_name,
        "wrapup_code_id": wrapup_code_id,
        "wrapup_code_name": wrapup_code_name,
        "origin_value": data.get("origin"),
        "destination_value": data.get("destination"),
        "created_time_ms": created_time_ms,
        "received_at": received_at,
        "raw_payload": json.dumps(payload),
    }

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
                    idle_code_id,
                    idle_code_name,
                    wrapup_code_id,
                    wrapup_code_name,
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
                    %(idle_code_id)s,
                    %(idle_code_name)s,
                    %(wrapup_code_id)s,
                    %(wrapup_code_name)s,
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
                parameters,
            )

            inserted = cursor.fetchone() is not None

            if agent_id and event_type.startswith("agent:"):
                current_state = (
                    data.get("currentState")
                    or ("logged-in" if event_type == "agent:login" else None)
                    or ("logged-out" if event_type == "agent:logout" else None)
                )

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
                        idle_code_id,
                        idle_code_name,
                        wrapup_code_id,
                        wrapup_code_name,
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
                        %(current_state_upsert)s,
                        %(idle_code_id)s,
                        %(idle_code_name)s,
                        %(wrapup_code_id)s,
                        %(wrapup_code_name)s,
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
                        idle_code_id = EXCLUDED.idle_code_id,
                        idle_code_name = EXCLUDED.idle_code_name,
                        wrapup_code_id = EXCLUDED.wrapup_code_id,
                        wrapup_code_name = EXCLUDED.wrapup_code_name,
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
                        **parameters,
                        "current_state_upsert": current_state,
                    },
                )

    return inserted


def upsert_contact_center_users(users: list[dict[str, Any]]) -> int:
    count = 0
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for user in users:
                user_id = user.get("id")
                if not user_id:
                    continue

                first_name = (user.get("firstName") or "").strip()
                last_name = (user.get("lastName") or "").strip()
                display_name = " ".join(
                    part for part in [first_name, last_name] if part
                ) or user.get("email") or user_id

                cursor.execute(
                    """
                    INSERT INTO contact_center_users (
                        user_id,
                        ci_user_id,
                        first_name,
                        last_name,
                        display_name,
                        email,
                        site_id,
                        primary_team_id,
                        team_ids,
                        contact_center_enabled,
                        active,
                        synced_at,
                        raw_payload
                    )
                    VALUES (
                        %(user_id)s,
                        %(ci_user_id)s,
                        %(first_name)s,
                        %(last_name)s,
                        %(display_name)s,
                        %(email)s,
                        %(site_id)s,
                        %(primary_team_id)s,
                        %(team_ids)s::jsonb,
                        %(contact_center_enabled)s,
                        %(active)s,
                        NOW(),
                        %(raw_payload)s::jsonb
                    )
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        ci_user_id = EXCLUDED.ci_user_id,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        display_name = EXCLUDED.display_name,
                        email = EXCLUDED.email,
                        site_id = EXCLUDED.site_id,
                        primary_team_id = EXCLUDED.primary_team_id,
                        team_ids = EXCLUDED.team_ids,
                        contact_center_enabled = EXCLUDED.contact_center_enabled,
                        active = EXCLUDED.active,
                        synced_at = NOW(),
                        raw_payload = EXCLUDED.raw_payload
                    """,
                    {
                        "user_id": user_id,
                        "ci_user_id": user.get("ciUserId"),
                        "first_name": first_name or None,
                        "last_name": last_name or None,
                        "display_name": display_name,
                        "email": user.get("email"),
                        "site_id": user.get("siteId"),
                        "primary_team_id": (
                            user.get("preferredSupervisorTeamId")
                            or (
                                (user.get("teamIds") or [None])[0]
                                if isinstance(user.get("teamIds"), list)
                                else None
                            )
                        ),
                        "team_ids": json.dumps(user.get("teamIds") or []),
                        "contact_center_enabled": user.get(
                            "contactCenterEnabled"
                        ),
                        "active": user.get("active"),
                        "raw_payload": json.dumps(user),
                    },
                )
                count += 1
    return count


def upsert_contact_center_teams(teams: list[dict[str, Any]]) -> int:
    count = 0
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for team in teams:
                team_id = team.get("id")
                team_name = team.get("name")
                if not team_id or not team_name:
                    continue

                cursor.execute(
                    """
                    INSERT INTO contact_center_teams (
                        team_id,
                        team_name,
                        team_type,
                        team_status,
                        site_id,
                        site_name,
                        active,
                        synced_at,
                        raw_payload
                    )
                    VALUES (
                        %(team_id)s,
                        %(team_name)s,
                        %(team_type)s,
                        %(team_status)s,
                        %(site_id)s,
                        %(site_name)s,
                        %(active)s,
                        NOW(),
                        %(raw_payload)s::jsonb
                    )
                    ON CONFLICT (team_id)
                    DO UPDATE SET
                        team_name = EXCLUDED.team_name,
                        team_type = EXCLUDED.team_type,
                        team_status = EXCLUDED.team_status,
                        site_id = EXCLUDED.site_id,
                        site_name = EXCLUDED.site_name,
                        active = EXCLUDED.active,
                        synced_at = NOW(),
                        raw_payload = EXCLUDED.raw_payload
                    """,
                    {
                        "team_id": team_id,
                        "team_name": team_name,
                        "team_type": team.get("teamType"),
                        "team_status": team.get("teamStatus"),
                        "site_id": team.get("siteId"),
                        "site_name": team.get("siteName"),
                        "active": team.get("active"),
                        "raw_payload": json.dumps(team),
                    },
                )
                count += 1
    return count


def upsert_contact_center_queues(queues: list[dict[str, Any]]) -> int:
    count = 0
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for queue in queues:
                queue_id = queue.get("id")
                queue_name = queue.get("name")
                if not queue_id or not queue_name:
                    continue

                cursor.execute(
                    """
                    INSERT INTO contact_center_queues (
                        queue_id,
                        queue_name,
                        queue_type,
                        channel_type,
                        routing_type,
                        active,
                        synced_at,
                        raw_payload
                    )
                    VALUES (
                        %(queue_id)s,
                        %(queue_name)s,
                        %(queue_type)s,
                        %(channel_type)s,
                        %(routing_type)s,
                        %(active)s,
                        NOW(),
                        %(raw_payload)s::jsonb
                    )
                    ON CONFLICT (queue_id)
                    DO UPDATE SET
                        queue_name = EXCLUDED.queue_name,
                        queue_type = EXCLUDED.queue_type,
                        channel_type = EXCLUDED.channel_type,
                        routing_type = EXCLUDED.routing_type,
                        active = EXCLUDED.active,
                        synced_at = NOW(),
                        raw_payload = EXCLUDED.raw_payload
                    """,
                    {
                        "queue_id": queue_id,
                        "queue_name": queue_name,
                        "queue_type": queue.get("queueType"),
                        "channel_type": queue.get("channelType"),
                        "routing_type": (
                            queue.get("queueRoutingType")
                            or queue.get("routingType")
                        ),
                        "active": queue.get("active"),
                        "raw_payload": json.dumps(queue),
                    },
                )
                count += 1
    return count


def get_lookup_counts() -> dict[str, int]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM contact_center_users) AS users,
                    (SELECT COUNT(*) FROM contact_center_teams) AS teams,
                    (SELECT COUNT(*) FROM contact_center_queues) AS queues,
                    (SELECT COUNT(*) FROM auxiliary_codes) AS auxiliary_codes
                """
            )
            row = cursor.fetchone()
            return dict(row)


def list_auxiliary_codes(
    code_type: str | None = None,
) -> list[dict[str, Any]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if code_type:
                cursor.execute(
                    """
                    SELECT *
                    FROM auxiliary_codes
                    WHERE code_type = %s
                    ORDER BY code_name
                    """,
                    (code_type,),
                )
            else:
                cursor.execute(
                    """
                    SELECT *
                    FROM auxiliary_codes
                    ORDER BY code_type, code_name
                    """
                )
            return list(cursor.fetchall())


def list_recent_events(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    e.event_id,
                    e.event_type,
                    e.agent_id,
                    e.agent_ci_user_id,
                    user_lookup.display_name AS agent_name,
                    user_lookup.email AS agent_email,
                    e.task_id,
                    e.queue_id,
                    queue_lookup.queue_name,
                    COALESCE(
                        e.team_id,
                        user_lookup.primary_team_id
                    ) AS team_id,
                    team_lookup.team_name,
                    team_lookup.site_name,
                    e.channel_id,
                    e.channel_type,
                    e.current_state,
                    e.idle_code_id,
                    COALESCE(
                        e.idle_code_name,
                        idle_lookup.code_name
                    ) AS idle_code_name,
                    e.wrapup_code_id,
                    COALESCE(
                        e.wrapup_code_name,
                        wrapup_lookup.code_name
                    ) AS wrapup_code_name,
                    e.origin_value AS origin,
                    e.destination_value AS destination,
                    e.occurred_at,
                    e.received_at,
                    e.raw_payload
                FROM agent_state_events e
                LEFT JOIN LATERAL (
                    SELECT
                        u.display_name,
                        u.email,
                        u.primary_team_id
                    FROM contact_center_users u
                    WHERE u.ci_user_id = e.agent_ci_user_id
                       OR u.user_id = e.agent_id
                    ORDER BY
                        CASE
                            WHEN u.ci_user_id = e.agent_ci_user_id THEN 0
                            ELSE 1
                        END
                    LIMIT 1
                ) user_lookup ON TRUE
                LEFT JOIN contact_center_teams team_lookup
                    ON team_lookup.team_id = COALESCE(
                        e.team_id,
                        user_lookup.primary_team_id
                    )
                LEFT JOIN contact_center_queues queue_lookup
                    ON queue_lookup.queue_id = e.queue_id
                LEFT JOIN auxiliary_codes idle_lookup
                    ON idle_lookup.auxiliary_code_id = e.idle_code_id
                LEFT JOIN auxiliary_codes wrapup_lookup
                    ON wrapup_lookup.auxiliary_code_id = e.wrapup_code_id
                ORDER BY e.received_at DESC
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
                    c.agent_id,
                    c.channel_type,
                    c.agent_ci_user_id,
                    user_lookup.display_name AS agent_name,
                    user_lookup.email AS agent_email,
                    c.task_id,
                    c.queue_id,
                    queue_lookup.queue_name,
                    COALESCE(
                        c.team_id,
                        user_lookup.primary_team_id
                    ) AS team_id,
                    team_lookup.team_name,
                    team_lookup.site_name,
                    c.channel_id,
                    c.current_state,
                    c.idle_code_id,
                    COALESCE(
                        c.idle_code_name,
                        idle_lookup.code_name
                    ) AS idle_code_name,
                    c.wrapup_code_id,
                    COALESCE(
                        c.wrapup_code_name,
                        wrapup_lookup.code_name
                    ) AS wrapup_code_name,
                    c.origin_value AS origin,
                    c.destination_value AS destination,
                    c.state_started_at,
                    EXTRACT(
                        EPOCH FROM (NOW() - c.state_started_at)
                    )::BIGINT AS state_duration_seconds,
                    c.source_created_time_ms,
                    c.last_event_id,
                    c.updated_at
                FROM current_agent_states c
                LEFT JOIN LATERAL (
                    SELECT
                        u.display_name,
                        u.email,
                        u.primary_team_id
                    FROM contact_center_users u
                    WHERE u.ci_user_id = c.agent_ci_user_id
                       OR u.user_id = c.agent_id
                    ORDER BY
                        CASE
                            WHEN u.ci_user_id = c.agent_ci_user_id THEN 0
                            ELSE 1
                        END
                    LIMIT 1
                ) user_lookup ON TRUE
                LEFT JOIN contact_center_teams team_lookup
                    ON team_lookup.team_id = COALESCE(
                        c.team_id,
                        user_lookup.primary_team_id
                    )
                LEFT JOIN contact_center_queues queue_lookup
                    ON queue_lookup.queue_id = c.queue_id
                LEFT JOIN auxiliary_codes idle_lookup
                    ON idle_lookup.auxiliary_code_id = c.idle_code_id
                LEFT JOIN auxiliary_codes wrapup_lookup
                    ON wrapup_lookup.auxiliary_code_id = c.wrapup_code_id
                ORDER BY c.current_state, c.agent_id
                """
            )
            return list(cursor.fetchall())
