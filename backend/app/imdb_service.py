"""Thin wrapper around `imdbinfo`.

All blocking IMDB I/O lives here. FastAPI handlers should invoke these functions
via ``asyncio.to_thread`` since imdbinfo is synchronous.

We previously used ``cinemagoer`` (the package formerly known as IMDbPY), but its
parsers broke after IMDB's late-2025 redesign and the addition of AWS WAF. The
``imdbinfo`` package (by the same author who maintains cinemagoer) is the
recommended successor: it has a built-in AWS WAF solver and returns pydantic
models directly.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from imdbinfo import search_title as _imdb_search_title
from imdbinfo.exceptions import HTTPError, WAFError
from imdbinfo.parsers import parse_json_bulked_episodes, parse_json_movie
from imdbinfo.services import (
    _delete_waf_cookie_file,
    request_json_url as _imdb_request_json_url,
)
import imdbinfo.services as _imdb_services

from .models import (
    ActorEpisodesResult,
    CastMember,
    EpisodeAppearance,
    OverlapResult,
    SharedActor,
    TitleDetail,
    TitleHit,
    TitleSummary,
)

logger = logging.getLogger(__name__)

# Pin WAF cookie storage to backend/.cache regardless of process cwd.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_WAF_CACHE_DIR = _BACKEND_ROOT / ".cache" / "imdbinfo"
_WAF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_imdb_services._WAF_COOKIE_FILE = _WAF_CACHE_DIR / "waf_cookies.json"

_RETRYABLE_STATUS = frozenset({202, 429, 503})


def _imdb_page_url(path: str) -> str:
    """Build an IMDB page URL without imdbinfo's empty-locale ``//`` bug."""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"https://www.imdb.com{path}"


def _request_json_url(url: str, *, retries: int = 4) -> Any:
    """Fetch embedded JSON from an IMDB page with retries on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return _imdb_request_json_url(url)
        except (HTTPError, WAFError) as exc:
            last_exc = exc
            status = getattr(exc, "status_code", None)
            if status not in _RETRYABLE_STATUS or attempt == retries - 1:
                raise
            logger.warning(
                "IMDB fetch attempt %s/%s failed for %s (%s); refreshing WAF cookies",
                attempt + 1,
                retries,
                url,
                exc,
            )
            _delete_waf_cookie_file()
            time.sleep(1.5 * (2**attempt))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"IMDB fetch failed for {url}")


def _imdb_get_movie(imdb_id: str) -> Any:
    """Fetch title details using a corrected reference-page URL."""
    norm = _normalize_id(imdb_id)
    url = _imdb_page_url(f"/title/tt{norm}/reference")
    raw = _request_json_url(url)
    return parse_json_movie(raw)


# Process-lifetime cache of fully-projected TitleDetail objects, keyed by the
# normalized digit-only IMDB id.
_title_cache: dict[str, TitleDetail] = {}
_title_cache_lock = threading.Lock()

# Process-lifetime cache of per-actor episode lists within a TV series.
_episode_cache: dict[tuple[str, str], list[EpisodeAppearance]] = {}
_episode_cache_lock = threading.Lock()

# Cached bulk episode list per series + cast ids per episode (for actor filtering).
_series_episodes_cache: dict[str, list[Any]] = {}
_series_episodes_cache_lock = threading.Lock()
_episode_cast_ids_cache: dict[str, set[str]] = {}
_episode_cast_ids_cache_lock = threading.Lock()


class TitleNotFoundError(LookupError):
    """Raised when imdbinfo returns no data for an IMDB title id."""


def _normalize_id(imdb_id: str) -> str:
    """Strip a leading 'tt' / 'nm' and return only the digits.

    imdbinfo accepts either form, but we standardize on the bare digits at the
    cache key + API boundary.
    """
    s = imdb_id.strip().lower()
    if s.startswith(("tt", "nm")):
        s = s[2:]
    if not s.isdigit():
        raise ValueError(f"Invalid IMDB id: {imdb_id!r}")
    return s


_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def _normalize_kind(kind: str | None) -> str | None:
    """Convert imdbinfo's camelCase 'tvSeries' into space-separated 'tv series'.

    The frontend already title-cases space-separated tokens, so keeping the
    API output in the old cinemagoer style (``'tv series'``, ``'movie'``,
    ``'tv mini series'``) avoids a frontend change.
    """
    if not kind:
        return None
    return _CAMEL_RE.sub(" ", str(kind)).lower()


def _role_from_characters(characters: Any) -> str | None:
    if not characters:
        return None
    parts = [str(c).strip() for c in characters if c]
    parts = [p for p in parts if p]
    if not parts:
        return None
    return " / ".join(parts)


def _project_title_hit(brief: Any) -> TitleHit | None:
    """Project an imdbinfo ``MovieBriefInfo`` into a ``TitleHit``."""
    imdb_id = getattr(brief, "imdb_id", None)
    title = getattr(brief, "title", None)
    if not imdb_id or not title:
        return None
    year_raw = getattr(brief, "year", None)
    try:
        year_int: int | None = int(year_raw) if year_raw is not None else None
    except (TypeError, ValueError):
        year_int = None
    cover = getattr(brief, "cover_url", None)
    return TitleHit(
        imdb_id=str(imdb_id),
        title=str(title),
        year=year_int,
        kind=_normalize_kind(getattr(brief, "kind", None)),
        poster_url=str(cover) if cover else None,
    )


def _project_cast_member(person: Any) -> CastMember | None:
    """Project an imdbinfo ``CastMember`` into our own ``CastMember`` DTO."""
    person_id = getattr(person, "imdb_id", None)
    name = getattr(person, "name", None)
    if not person_id or not name:
        return None
    return CastMember(
        imdb_id=str(person_id),
        name=str(name),
        role=_role_from_characters(getattr(person, "characters", None)),
        headshot_url=getattr(person, "picture_url", None) or None,
    )


def _extract_cast_from_reference(movie: Any) -> list[Any]:
    """Pull actors out of an imdbinfo movie/series detail object.

    imdbinfo's ``get_movie`` hits IMDB's ``/title/.../reference`` page, where
    the cast list is capped at the page's top-billed ~50. We use this only as
    a fallback when the richer ``/fullcredits`` path fails.
    """
    categories = getattr(movie, "categories", None)
    if not isinstance(categories, dict):
        return []
    cast = list(categories.get("cast") or [])
    if not cast:
        for key in ("actor", "actress"):
            extra = categories.get(key)
            if extra:
                cast.extend(extra)
    return cast


def _project_fullcredits_item(item: dict[str, Any]) -> CastMember | None:
    """Project a single ``/fullcredits`` cast row into our DTO."""
    pid_raw = item.get("id")
    name = item.get("rowTitle")
    if not isinstance(pid_raw, str) or not name:
        return None
    pid = pid_raw[2:] if pid_raw.startswith("nm") else pid_raw
    if not pid.isdigit():
        return None
    image_props = item.get("imageProps") or {}
    image_model = image_props.get("imageModel") or {}
    headshot = image_model.get("url")
    ep_data = item.get("episodicCreditData")
    episodes: int | None = None
    if isinstance(ep_data, dict):
        raw_count = ep_data.get("episodeCount")
        if isinstance(raw_count, int):
            episodes = raw_count
        elif isinstance(raw_count, str) and raw_count.isdigit():
            episodes = int(raw_count)
    return CastMember(
        imdb_id=pid,
        name=str(name),
        role=_role_from_characters(item.get("characters")),
        headshot_url=str(headshot) if headshot else None,
        episodes=episodes,
    )


def _fetch_full_cast(imdb_id: str) -> list[CastMember]:
    """Fetch the broader cast list from IMDB's ``/fullcredits`` page.

    The fullcredits page embeds a JSON payload with ~260 cast members in its
    first page (vs the ~50 cap on ``/reference``). For typical titles this is
    plenty for an actor-overlap query without needing GraphQL pagination.

    Raises any underlying HTTP / parse errors; the caller is expected to
    fall back to the reference-page cast when this raises.
    """
    url = _imdb_page_url(f"/title/tt{imdb_id}/fullcredits/")
    raw = _request_json_url(url)

    categories = (
        raw.get("props", {})
        .get("pageProps", {})
        .get("contentData", {})
        .get("categories")
    )
    if not isinstance(categories, list):
        return []

    items: list[dict[str, Any]] = []
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        name = cat.get("name") or ""
        if name.lower() == "cast":
            section = cat.get("section") or {}
            raw_items = section.get("items") or []
            items = [it for it in raw_items if isinstance(it, dict)]
            break

    members: list[CastMember] = []
    seen: set[str] = set()
    for it in items:
        member = _project_fullcredits_item(it)
        if member is None or member.imdb_id in seen:
            continue
        seen.add(member.imdb_id)
        members.append(member)
    return members


def _get_series_episodes(title_id: str) -> list[Any]:
    """Return the bulk episode list for a TV series (cached)."""
    norm = _normalize_id(title_id)
    with _series_episodes_cache_lock:
        cached = _series_episodes_cache.get(norm)
    if cached is not None:
        return cached

    url = _imdb_page_url(
        f"/search/title/?count=250&series=tt{norm}&sort=release_date,asc"
    )
    raw = _request_json_url(url)
    episodes = parse_json_bulked_episodes(raw)
    with _series_episodes_cache_lock:
        _series_episodes_cache[norm] = episodes
    return episodes


def _episode_cast_person_ids(episode_id: str) -> set[str]:
    """Return the cast person ids credited on a single episode (cached)."""
    norm = _normalize_id(episode_id)
    with _episode_cast_ids_cache_lock:
        cached = _episode_cast_ids_cache.get(norm)
    if cached is not None:
        return cached

    members = _fetch_full_cast(norm)
    person_ids = {member.imdb_id for member in members}
    with _episode_cast_ids_cache_lock:
        _episode_cast_ids_cache[norm] = person_ids
    return person_ids


def _project_bulk_episode(ep: Any) -> EpisodeAppearance | None:
    """Project an imdbinfo ``BulkedEpisode`` into our episode DTO."""
    imdb_id = getattr(ep, "imdb_id", None)
    title = getattr(ep, "title", None)
    season = getattr(ep, "season_number", None)
    episode_no = getattr(ep, "episode_number", None)
    if not imdb_id or not title:
        return None
    try:
        season_int = int(season)
        episode_int = int(episode_no)
    except (TypeError, ValueError):
        return None
    return EpisodeAppearance(
        imdb_id=str(imdb_id),
        season=season_int,
        episode=episode_int,
        title=str(title),
    )


def fetch_actor_episodes_for_show(title_id: str, person_id: str) -> list[EpisodeAppearance]:
    """Return the episodes in which ``person_id`` appears in ``title_id``.

    IMDB's ``?nm=`` filter on the episodes page no longer works, so we load the
    series' episode list once and match against each episode's cast. Episode
    cast and the final per-actor result are cached for the process lifetime.
    """
    norm_title = _normalize_id(title_id)
    norm_person = _normalize_id(person_id)
    cache_key = (norm_title, norm_person)
    with _episode_cache_lock:
        cached = _episode_cache.get(cache_key)
    if cached is not None:
        return cached

    series_episodes = _get_series_episodes(norm_title)
    appearances: list[EpisodeAppearance] = []

    def _match_episode(ep: Any) -> EpisodeAppearance | None:
        ep_id = getattr(ep, "imdb_id", None)
        if not ep_id or norm_person not in _episode_cast_person_ids(str(ep_id)):
            return None
        return _project_bulk_episode(ep)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for match in pool.map(_match_episode, series_episodes):
            if match is not None:
                appearances.append(match)

    appearances.sort(key=lambda item: (item.season, item.episode))

    with _episode_cache_lock:
        _episode_cache[cache_key] = appearances
    return appearances


def get_actor_episodes(title_id: str, person_id: str) -> ActorEpisodesResult:
    """Fetch (and cache) the episodes a person appears in for a TV series."""
    norm_title = _normalize_id(title_id)
    norm_person = _normalize_id(person_id)
    return ActorEpisodesResult(
        title_id=norm_title,
        person_id=norm_person,
        episodes=fetch_actor_episodes_for_show(norm_title, norm_person),
    )


def search_titles(query: str, limit: int = 8) -> list[TitleHit]:
    """Search IMDB titles by name. Returns up to ``limit`` hits."""
    query = query.strip()
    if not query:
        return []
    result = _imdb_search_title(query)
    briefs = getattr(result, "titles", None) or []
    hits: list[TitleHit] = []
    for brief in briefs:
        hit = _project_title_hit(brief)
        if hit is not None:
            hits.append(hit)
        if len(hits) >= limit:
            break
    return hits


def get_title_with_cast(imdb_id: str) -> TitleDetail:
    """Fetch a title (movie or TV series) and its top-billed cast.

    Results are cached in-process for the lifetime of the server.
    """
    norm = _normalize_id(imdb_id)
    with _title_cache_lock:
        cached = _title_cache.get(norm)
    if cached is not None:
        return cached

    movie = _imdb_get_movie(norm)
    if movie is None:
        raise TitleNotFoundError(f"No IMDB title found for id {imdb_id!r}")

    title = getattr(movie, "title", None)
    if not title:
        raise TitleNotFoundError(f"IMDB title {imdb_id!r} has no title field")

    year_raw = getattr(movie, "year", None)
    try:
        year_int: int | None = int(year_raw) if year_raw is not None else None
    except (TypeError, ValueError):
        year_int = None

    members: list[CastMember] = []
    try:
        members = _fetch_full_cast(norm)
    except Exception as exc:
        logger.warning(
            "fullcredits fetch failed for %s, falling back to /reference cast: %s",
            norm,
            exc,
        )

    if not members:
        seen_ids: set[str] = set()
        for person in _extract_cast_from_reference(movie):
            m = _project_cast_member(person)
            if m is None or m.imdb_id in seen_ids:
                continue
            seen_ids.add(m.imdb_id)
            members.append(m)

    cover = getattr(movie, "cover_url", None)
    detail = TitleDetail(
        imdb_id=norm,
        title=str(title),
        year=year_int,
        kind=_normalize_kind(getattr(movie, "kind", None)),
        poster_url=str(cover) if cover else None,
        cast=members,
    )

    with _title_cache_lock:
        _title_cache[norm] = detail
    return detail


def overlap(ids: list[str]) -> OverlapResult:
    """Return the actors that appear in every one of the requested titles.

    ``ids`` must contain at least two distinct IMDB title ids. The output's
    ``titles`` list preserves the input order, and each ``SharedActor``'s
    ``roles`` / ``episodes`` lists are aligned to that same order.
    """
    if len(ids) < 2:
        raise ValueError("overlap() requires at least 2 title ids")

    # Normalize + dedupe while preserving order, so we don't compare a title
    # against itself.
    normalized: list[str] = []
    seen_ids: set[str] = set()
    for raw_id in ids:
        norm = _normalize_id(raw_id)
        if norm in seen_ids:
            continue
        seen_ids.add(norm)
        normalized.append(norm)

    if len(normalized) < 2:
        raise ValueError("overlap() requires at least 2 distinct title ids")

    # Fetch every title's projected cast (cache makes repeat calls cheap).
    details: list[TitleDetail] = [get_title_with_cast(n) for n in normalized]

    # casts_by_id[i][person_id] = CastMember projection in title i
    casts_by_id: list[dict[str, CastMember]] = [
        {m.imdb_id: m for m in d.cast} for d in details
    ]

    # Start from the smallest cast for efficiency, then intersect.
    smallest_index = min(range(len(details)), key=lambda i: len(details[i].cast))
    candidate_ids = set(casts_by_id[smallest_index].keys())
    for i, cast_map in enumerate(casts_by_id):
        if i == smallest_index:
            continue
        candidate_ids &= set(cast_map.keys())
        if not candidate_ids:
            break

    shared: list[SharedActor] = []
    # Preserve the order in which actors first appear in title 0 (caller's
    # intuition: top-billed in their primary pick floats up).
    primary_cast = details[0].cast
    seen_shared: set[str] = set()
    for primary in primary_cast:
        pid = primary.imdb_id
        if pid not in candidate_ids or pid in seen_shared:
            continue
        seen_shared.add(pid)

        roles: list[str | None] = []
        episodes: list[int | None] = []
        headshot: str | None = None
        for cast_map in casts_by_id:
            member = cast_map[pid]
            roles.append(member.role)
            episodes.append(member.episodes)
            if not headshot and member.headshot_url:
                headshot = member.headshot_url

        shared.append(
            SharedActor(
                imdb_id=pid,
                name=primary.name,
                headshot_url=headshot,
                roles=roles,
                episodes=episodes,
            )
        )

    titles = [
        TitleSummary(
            imdb_id=d.imdb_id,
            title=d.title,
            year=d.year,
            kind=d.kind,
            poster_url=d.poster_url,
        )
        for d in details
    ]
    return OverlapResult(titles=titles, shared=shared)
