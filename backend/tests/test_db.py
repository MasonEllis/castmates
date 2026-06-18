"""Tests for the SQLite persistence layer."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import db
from app.models import CastMember, EpisodeAppearance, TitleDetail


@pytest.fixture()
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db.configure_db_path(db_file)
    db.init_db()
    yield db_file
    db.configure_db_path(db.DEFAULT_DB_PATH)


def test_title_cast_round_trip_and_actor_titles(temp_db: Path) -> None:
    detail = TitleDetail(
        imdb_id="0903747",
        title="Breaking Bad",
        year=2008,
        kind="tv series",
        poster_url="https://example.com/bb.jpg",
        cast=[
            CastMember(
                imdb_id="0186505",
                name="Bryan Cranston",
                role="Walter White",
                headshot_url=None,
                episodes=62,
            ),
            CastMember(
                imdb_id="0002064",
                name="Giancarlo Esposito",
                role="Gus Fring",
                headshot_url=None,
                episodes=26,
            ),
        ],
    )
    db.upsert_title_detail(detail)

    loaded = db.get_title_detail("0903747")
    assert loaded is not None
    assert loaded.title == "Breaking Bad"
    assert len(loaded.cast) == 2
    assert loaded.cast[0].name == "Bryan Cranston"

    actor_titles = db.get_actor_titles("0002064")
    assert actor_titles.actor_id == "0002064"
    assert len(actor_titles.titles) == 1
    assert actor_titles.titles[0].title == "Breaking Bad"
    assert actor_titles.titles[0].role == "Gus Fring"
    assert actor_titles.titles[0].episodes == 26


def test_retention_purges_stale_title_cast(temp_db: Path) -> None:
    detail = TitleDetail(
        imdb_id="0212671",
        title="Malcolm in the Middle",
        year=2000,
        kind="tv series",
        poster_url=None,
        cast=[
            CastMember(
                imdb_id="0186505",
                name="Bryan Cranston",
                role="Hal",
                headshot_url=None,
                episodes=151,
            ),
        ],
    )
    db.upsert_title_detail(detail)

    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    conn = sqlite3.connect(temp_db)
    conn.execute("UPDATE titles SET cast_fetched_at = ?", (stale,))
    conn.execute("UPDATE title_cast SET fetched_at = ?", (stale,))
    conn.commit()
    conn.close()

    db.purge_expired()
    assert db.get_title_detail("0212671") is None
    assert db.get_actor_titles("0186505").titles == []


def test_actor_episodes_and_episode_cast_round_trip(temp_db: Path) -> None:
    episodes = [
        EpisodeAppearance(imdb_id="0959621", season=1, episode=1, title="Pilot"),
        EpisodeAppearance(imdb_id="1054724", season=1, episode=2, title="Cat's in the Bag..."),
    ]
    db.upsert_actor_episodes("0903747", "0186505", episodes)
    db.upsert_episode_cast_ids("0959621", {"0186505", "0002064"})

    loaded_eps = db.get_actor_episodes("0903747", "0186505")
    assert loaded_eps is not None
    assert len(loaded_eps) == 2
    assert loaded_eps[0].title == "Pilot"

    cast_ids = db.get_episode_cast_ids("0959621")
    assert cast_ids == {"0186505", "0002064"}


def test_empty_actor_episodes_are_stored(temp_db: Path) -> None:
    db.upsert_actor_episodes("0903747", "0186505", [])

    loaded_eps = db.get_actor_episodes("0903747", "0186505")
    assert loaded_eps == []


def test_episode_lists_surface_on_title_and_actor_queries(temp_db: Path) -> None:
    detail = TitleDetail(
        imdb_id="0903747",
        title="Breaking Bad",
        year=2008,
        kind="tv series",
        poster_url=None,
        cast=[
            CastMember(
                imdb_id="0186505",
                name="Bryan Cranston",
                role="Walter White",
                headshot_url=None,
                episodes=62,
            ),
            CastMember(
                imdb_id="0002064",
                name="Giancarlo Esposito",
                role="Gus Fring",
                headshot_url=None,
                episodes=26,
            ),
        ],
    )
    db.upsert_title_detail(detail)
    db.upsert_actor_episodes(
        "0903747",
        "0186505",
        [
            EpisodeAppearance(imdb_id="0959621", season=1, episode=1, title="Pilot"),
        ],
    )

    loaded_title = db.get_title_detail("0903747")
    assert loaded_title is not None
    cranston = loaded_title.cast[0]
    esposito = loaded_title.cast[1]
    assert cranston.episode_list is not None
    assert len(cranston.episode_list) == 1
    assert cranston.episode_list[0].title == "Pilot"
    assert esposito.episode_list is None

    actor_titles = db.get_actor_titles("0186505")
    assert len(actor_titles.titles) == 1
    credit = actor_titles.titles[0]
    assert credit.episode_list is not None
    assert credit.episode_list[0].imdb_id == "0959621"


def test_legacy_person_schema_migrates_to_actor_names(temp_db: Path) -> None:
    conn = sqlite3.connect(temp_db)
    conn.executescript(
        """
        CREATE TABLE persons (
            imdb_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            headshot_url TEXT
        );
        CREATE TABLE titles (
            imdb_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            year INTEGER,
            kind TEXT,
            poster_url TEXT,
            cast_fetched_at TEXT NOT NULL
        );
        CREATE TABLE title_cast (
            title_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            role TEXT,
            episodes INTEGER,
            billing_order INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (title_id, person_id)
        );
        """
    )
    conn.close()

    db.init_db()

    conn = sqlite3.connect(temp_db)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "actors" in tables
    assert "persons" not in tables
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(title_cast)").fetchall()
    }
    assert "actor_id" in columns
    assert "person_id" not in columns
    conn.close()