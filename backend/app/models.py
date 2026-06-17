"""Pydantic response models for the API.

Kept intentionally small for v0 — only the fields the frontend currently uses.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TitleHit(BaseModel):
    """A single search-result row for a movie or TV series."""

    imdb_id: str = Field(..., description="IMDB title id without the 'tt' prefix.")
    title: str
    year: int | None = None
    kind: str | None = Field(
        None,
        description="IMDB 'kind' value, e.g. 'movie', 'tv series', 'tv mini series'.",
    )
    poster_url: str | None = Field(
        None,
        description="URL of the title's cover/poster image, when IMDB provides one.",
    )


class CastMember(BaseModel):
    """One actor as they appear in a single title."""

    imdb_id: str = Field(..., description="IMDB person id without the 'nm' prefix.")
    name: str
    role: str | None = None
    headshot_url: str | None = None
    episodes: int | None = Field(
        None,
        description="Number of episodes the actor appears in. None for movies.",
    )


class TitleDetail(BaseModel):
    """Full title info with its cast attached."""

    imdb_id: str
    title: str
    year: int | None = None
    kind: str | None = None
    poster_url: str | None = None
    cast: list[CastMember]


class TitleSummary(BaseModel):
    imdb_id: str
    title: str
    year: int | None = None
    kind: str | None = None
    poster_url: str | None = None


class SharedActor(BaseModel):
    """An actor that appears in every requested title.

    ``roles`` and ``episodes`` are parallel to the ``titles`` array in the
    enclosing ``OverlapResult`` — index ``i`` describes the actor's part in
    ``titles[i]``.
    """

    imdb_id: str
    name: str
    headshot_url: str | None = None
    roles: list[str | None] = Field(default_factory=list)
    episodes: list[int | None] = Field(default_factory=list)


class OverlapResult(BaseModel):
    """Response for the overlap endpoint.

    Supports an arbitrary number of titles (minimum two). ``shared`` contains
    only actors present in *every* requested title.
    """

    titles: list[TitleSummary]
    shared: list[SharedActor]
