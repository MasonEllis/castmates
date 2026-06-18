"""SQLite persistence for IMDB title cast and actor credits.

Answers three questions from local data once fetched:
  1. What actors are in this title?
  2. What titles is this actor in?
  3. Which episodes does an actor appear in for a given TV show?

Rows older than ``RETENTION_DAYS`` are purged on init and before writes.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .models import (
    CastMember,
    EpisodeAppearance,
    PersonTitleCredit,
    PersonTitlesResult,
    TitleDetail,
)

logger = logging.getLogger(__name__)

RETENTION_DAYS = 7

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = _BACKEND_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "castmates.db"

_db_path: Path = DEFAULT_DB_PATH
_lock = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _cutoff_iso() -> str:
    return _iso(_utc_now() - timedelta(days=RETENTION_DAYS))


def configure_db_path(path: Path | str) -> None:
    """Override the database file path (used in tests)."""
    global _db_path
    _db_path = Path(path)


def _connect() -> sqlite3.Connection:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if needed and purge expired rows."""
    with _lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS titles (
                    imdb_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    year INTEGER,
                    kind TEXT,
                    poster_url TEXT,
                    cast_fetched_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS persons (
                    imdb_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    headshot_url TEXT
                );

                CREATE TABLE IF NOT EXISTS title_cast (
                    title_id TEXT NOT NULL REFERENCES titles(imdb_id) ON DELETE CASCADE,
                    person_id TEXT NOT NULL REFERENCES persons(imdb_id) ON DELETE CASCADE,
                    role TEXT,
                    episodes INTEGER,
                    billing_order INTEGER NOT NULL DEFAULT 0,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (title_id, person_id)
                );

                CREATE TABLE IF NOT EXISTS actor_episode_fetches (
                    title_id TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (title_id, person_id)
                );

                CREATE TABLE IF NOT EXISTS actor_episodes (
                    title_id TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    episode_id TEXT NOT NULL,
                    season INTEGER NOT NULL,
                    episode INTEGER NOT NULL,
                    episode_title TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (title_id, person_id, episode_id)
                );

                CREATE TABLE IF NOT EXISTS episode_cast (
                    episode_id TEXT PRIMARY KEY,
                    fetched_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS episode_cast_members (
                    episode_id TEXT NOT NULL REFERENCES episode_cast(episode_id) ON DELETE CASCADE,
                    person_id TEXT NOT NULL,
                    PRIMARY KEY (episode_id, person_id)
                );

                CREATE INDEX IF NOT EXISTS idx_title_cast_person
                    ON title_cast(person_id, fetched_at);
                CREATE INDEX IF NOT EXISTS idx_actor_episodes_lookup
                    ON actor_episodes(title_id, person_id, fetched_at);
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO actor_episode_fetches (title_id, person_id, fetched_at)
                SELECT title_id, person_id, MAX(fetched_at)
                FROM actor_episodes
                GROUP BY title_id, person_id
                """
            )
            conn.commit()
            _purge_expired_locked(conn)
        finally:
            conn.close()


def purge_expired() -> None:
    with _lock:
        conn = _connect()
        try:
            _purge_expired_locked(conn)
            conn.commit()
        finally:
            conn.close()


def _is_tv_kind(kind: str | None) -> bool:
    return kind is not None and kind.startswith("tv")


def _purge_expired_locked(conn: sqlite3.Connection) -> None:
    cutoff = _cutoff_iso()
    conn.execute("DELETE FROM actor_episode_fetches WHERE fetched_at < ?", (cutoff,))
    conn.execute("DELETE FROM actor_episodes WHERE fetched_at < ?", (cutoff,))
    conn.execute(
        """
        DELETE FROM episode_cast_members
        WHERE episode_id IN (SELECT episode_id FROM episode_cast WHERE fetched_at < ?)
        """,
        (cutoff,),
    )
    conn.execute("DELETE FROM episode_cast WHERE fetched_at < ?", (cutoff,))
    conn.execute("DELETE FROM title_cast WHERE fetched_at < ?", (cutoff,))
    conn.execute("DELETE FROM titles WHERE cast_fetched_at < ?", (cutoff,))
    conn.execute(
        """
        DELETE FROM persons
        WHERE imdb_id NOT IN (SELECT person_id FROM title_cast)
          AND imdb_id NOT IN (SELECT person_id FROM actor_episodes)
          AND imdb_id NOT IN (SELECT person_id FROM actor_episode_fetches)
        """
    )


def _episode_rows_to_map(
    rows: Iterable[sqlite3.Row],
) -> dict[tuple[str, str], list[EpisodeAppearance]]:
    grouped: dict[tuple[str, str], list[EpisodeAppearance]] = {}
    for row in rows:
        key = (row["title_id"], row["person_id"])
        grouped.setdefault(key, []).append(
            EpisodeAppearance(
                imdb_id=row["episode_id"],
                season=row["season"],
                episode=row["episode"],
                title=row["episode_title"],
            )
        )
    return grouped


def _scoped_id_clauses(
    *,
    title_id: str | None,
    person_id: str | None,
    title_ids: Iterable[str] | None,
    person_ids: Iterable[str] | None,
) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    if title_id is not None:
        clauses.append("title_id = ?")
        params.append(title_id)
    elif title_ids is not None:
        ids = list(title_ids)
        if not ids:
            return [], []
        placeholders = ",".join("?" * len(ids))
        clauses.append(f"title_id IN ({placeholders})")
        params.extend(ids)

    if person_id is not None:
        clauses.append("person_id = ?")
        params.append(person_id)
    elif person_ids is not None:
        ids = list(person_ids)
        if not ids:
            return [], []
        placeholders = ",".join("?" * len(ids))
        clauses.append(f"person_id IN ({placeholders})")
        params.extend(ids)

    return clauses, params


def _load_episode_map(
    conn: sqlite3.Connection,
    cutoff: str,
    *,
    title_id: str | None = None,
    person_id: str | None = None,
    title_ids: Iterable[str] | None = None,
    person_ids: Iterable[str] | None = None,
) -> dict[tuple[str, str], list[EpisodeAppearance]]:
    """Return stored episode lists for resolved actor/show pairs only."""
    scope_clauses, scope_params = _scoped_id_clauses(
        title_id=title_id,
        person_id=person_id,
        title_ids=title_ids,
        person_ids=person_ids,
    )
    if not scope_clauses:
        return {}

    fetch_where = " AND ".join(["fetched_at >= ?", *scope_clauses])
    fetch_rows = conn.execute(
        f"""
        SELECT title_id, person_id
        FROM actor_episode_fetches
        WHERE {fetch_where}
        """,
        [cutoff, *scope_params],
    ).fetchall()
    if not fetch_rows:
        return {}

    episode_where = " AND ".join(["fetched_at >= ?", *scope_clauses])
    episode_rows = conn.execute(
        f"""
        SELECT title_id, person_id, episode_id, season, episode, episode_title
        FROM actor_episodes
        WHERE {episode_where}
        ORDER BY title_id ASC, person_id ASC, season ASC, episode ASC
        """,
        [cutoff, *scope_params],
    ).fetchall()
    episodes_by_pair = _episode_rows_to_map(episode_rows)

    return {
        (row["title_id"], row["person_id"]): episodes_by_pair.get(
            (row["title_id"], row["person_id"]), []
        )
        for row in fetch_rows
    }


def get_title_detail(imdb_id: str) -> TitleDetail | None:
    """Return a stored title + cast if still within the retention window."""
    cutoff = _cutoff_iso()
    with _lock:
        conn = _connect()
        try:
            title_row = conn.execute(
                """
                SELECT imdb_id, title, year, kind, poster_url
                FROM titles
                WHERE imdb_id = ? AND cast_fetched_at >= ?
                """,
                (imdb_id, cutoff),
            ).fetchone()
            if title_row is None:
                return None

            cast_rows = conn.execute(
                """
                SELECT
                    p.imdb_id,
                    p.name,
                    p.headshot_url,
                    tc.role,
                    tc.episodes,
                    tc.billing_order
                FROM title_cast tc
                JOIN persons p ON p.imdb_id = tc.person_id
                WHERE tc.title_id = ? AND tc.fetched_at >= ?
                ORDER BY tc.billing_order ASC
                """,
                (imdb_id, cutoff),
            ).fetchall()
            if not cast_rows:
                return None

            episode_map: dict[tuple[str, str], list[EpisodeAppearance]] = {}
            if _is_tv_kind(title_row["kind"]):
                episode_map = _load_episode_map(
                    conn,
                    cutoff,
                    title_id=imdb_id,
                    person_ids=[row["imdb_id"] for row in cast_rows],
                )

            cast = [
                CastMember(
                    imdb_id=row["imdb_id"],
                    name=row["name"],
                    role=row["role"],
                    headshot_url=row["headshot_url"],
                    episodes=row["episodes"],
                    episode_list=episode_map.get((imdb_id, row["imdb_id"])),
                )
                for row in cast_rows
            ]
            return TitleDetail(
                imdb_id=title_row["imdb_id"],
                title=title_row["title"],
                year=title_row["year"],
                kind=title_row["kind"],
                poster_url=title_row["poster_url"],
                cast=cast,
            )
        finally:
            conn.close()


def upsert_title_detail(detail: TitleDetail) -> None:
    """Insert or replace a title and its full cast."""
    fetched_at = _iso(_utc_now())
    with _lock:
        conn = _connect()
        try:
            _purge_expired_locked(conn)
            conn.execute(
                """
                INSERT INTO titles (imdb_id, title, year, kind, poster_url, cast_fetched_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(imdb_id) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    kind = excluded.kind,
                    poster_url = excluded.poster_url,
                    cast_fetched_at = excluded.cast_fetched_at
                """,
                (
                    detail.imdb_id,
                    detail.title,
                    detail.year,
                    detail.kind,
                    detail.poster_url,
                    fetched_at,
                ),
            )
            conn.execute("DELETE FROM title_cast WHERE title_id = ?", (detail.imdb_id,))
            for order, member in enumerate(detail.cast):
                conn.execute(
                    """
                    INSERT INTO persons (imdb_id, name, headshot_url)
                    VALUES (?, ?, ?)
                    ON CONFLICT(imdb_id) DO UPDATE SET
                        name = excluded.name,
                        headshot_url = COALESCE(excluded.headshot_url, persons.headshot_url)
                    """,
                    (member.imdb_id, member.name, member.headshot_url),
                )
                conn.execute(
                    """
                    INSERT INTO title_cast (
                        title_id, person_id, role, episodes, billing_order, fetched_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detail.imdb_id,
                        member.imdb_id,
                        member.role,
                        member.episodes,
                        order,
                        fetched_at,
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def get_person_titles(person_id: str) -> PersonTitlesResult:
    """List titles this actor appears in (from stored cast rows only)."""
    cutoff = _cutoff_iso()
    with _lock:
        conn = _connect()
        try:
            name_row = conn.execute(
                "SELECT name FROM persons WHERE imdb_id = ?",
                (person_id,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT
                    t.imdb_id,
                    t.title,
                    t.year,
                    t.kind,
                    t.poster_url,
                    tc.role,
                    tc.episodes
                FROM title_cast tc
                JOIN titles t ON t.imdb_id = tc.title_id
                WHERE tc.person_id = ?
                  AND tc.fetched_at >= ?
                  AND t.cast_fetched_at >= ?
                ORDER BY t.title COLLATE NOCASE ASC
                """,
                (person_id, cutoff, cutoff),
            ).fetchall()
            tv_title_ids = [
                row["imdb_id"] for row in rows if _is_tv_kind(row["kind"])
            ]
            episode_map = _load_episode_map(
                conn,
                cutoff,
                person_id=person_id,
                title_ids=tv_title_ids,
            )

            titles = [
                PersonTitleCredit(
                    imdb_id=row["imdb_id"],
                    title=row["title"],
                    year=row["year"],
                    kind=row["kind"],
                    poster_url=row["poster_url"],
                    role=row["role"],
                    episodes=row["episodes"],
                    episode_list=episode_map.get((row["imdb_id"], person_id))
                    if _is_tv_kind(row["kind"])
                    else None,
                )
                for row in rows
            ]
            return PersonTitlesResult(
                person_id=person_id,
                name=name_row["name"] if name_row else None,
                titles=titles,
            )
        finally:
            conn.close()


def get_actor_episodes(title_id: str, person_id: str) -> list[EpisodeAppearance] | None:
    cutoff = _cutoff_iso()
    with _lock:
        conn = _connect()
        try:
            fetched = conn.execute(
                """
                SELECT 1
                FROM actor_episode_fetches
                WHERE title_id = ? AND person_id = ? AND fetched_at >= ?
                """,
                (title_id, person_id, cutoff),
            ).fetchone()
            if fetched is None:
                return None

            rows = conn.execute(
                """
                SELECT episode_id, season, episode, episode_title
                FROM actor_episodes
                WHERE title_id = ? AND person_id = ? AND fetched_at >= ?
                ORDER BY season ASC, episode ASC
                """,
                (title_id, person_id, cutoff),
            ).fetchall()
            return [
                EpisodeAppearance(
                    imdb_id=row["episode_id"],
                    season=row["season"],
                    episode=row["episode"],
                    title=row["episode_title"],
                )
                for row in rows
            ]
        finally:
            conn.close()


def upsert_actor_episodes(
    title_id: str,
    person_id: str,
    episodes: Iterable[EpisodeAppearance],
) -> None:
    fetched_at = _iso(_utc_now())
    episode_list = list(episodes)
    with _lock:
        conn = _connect()
        try:
            _purge_expired_locked(conn)
            conn.execute(
                "DELETE FROM actor_episodes WHERE title_id = ? AND person_id = ?",
                (title_id, person_id),
            )
            conn.execute(
                """
                INSERT INTO actor_episode_fetches (title_id, person_id, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(title_id, person_id) DO UPDATE SET
                    fetched_at = excluded.fetched_at
                """,
                (title_id, person_id, fetched_at),
            )
            for ep in episode_list:
                conn.execute(
                    """
                    INSERT INTO actor_episodes (
                        title_id, person_id, episode_id, season, episode,
                        episode_title, fetched_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title_id,
                        person_id,
                        ep.imdb_id,
                        ep.season,
                        ep.episode,
                        ep.title,
                        fetched_at,
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def get_episode_cast_ids(episode_id: str) -> set[str] | None:
    cutoff = _cutoff_iso()
    with _lock:
        conn = _connect()
        try:
            header = conn.execute(
                "SELECT episode_id FROM episode_cast WHERE episode_id = ? AND fetched_at >= ?",
                (episode_id, cutoff),
            ).fetchone()
            if header is None:
                return None
            rows = conn.execute(
                "SELECT person_id FROM episode_cast_members WHERE episode_id = ?",
                (episode_id,),
            ).fetchall()
            return {row["person_id"] for row in rows}
        finally:
            conn.close()


def upsert_episode_cast_ids(episode_id: str, person_ids: Iterable[str]) -> None:
    fetched_at = _iso(_utc_now())
    ids = list(person_ids)
    with _lock:
        conn = _connect()
        try:
            _purge_expired_locked(conn)
            conn.execute(
                """
                INSERT INTO episode_cast (episode_id, fetched_at)
                VALUES (?, ?)
                ON CONFLICT(episode_id) DO UPDATE SET fetched_at = excluded.fetched_at
                """,
                (episode_id, fetched_at),
            )
            conn.execute(
                "DELETE FROM episode_cast_members WHERE episode_id = ?",
                (episode_id,),
            )
            conn.executemany(
                "INSERT INTO episode_cast_members (episode_id, person_id) VALUES (?, ?)",
                [(episode_id, pid) for pid in ids],
            )
            conn.commit()
        finally:
            conn.close()