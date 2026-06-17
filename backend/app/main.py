"""FastAPI app exposing IMDB title search and cast overlap endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import imdb_service
from .models import OverlapResult, TitleDetail, TitleHit

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Actors Overlap API",
    version="0.1.0",
    description=(
        "v0 of a Kevin-Bacon-style app. Given two IMDB titles, returns the cast "
        "members that appear in both. Data is fetched via the cinemagoer library."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/search", response_model=list[TitleHit])
async def search(
    q: Annotated[str, Query(min_length=1, description="Movie or TV title to search for.")],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[TitleHit]:
    try:
        return await asyncio.to_thread(imdb_service.search_titles, q, limit)
    except Exception as exc:
        logger.exception("search failed for q=%r", q)
        raise HTTPException(status_code=502, detail=f"IMDB search failed: {exc}") from exc


@app.get("/api/title/{imdb_id}", response_model=TitleDetail)
async def title(imdb_id: str) -> TitleDetail:
    try:
        return await asyncio.to_thread(imdb_service.get_title_with_cast, imdb_id)
    except imdb_service.TitleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("get_title failed for imdb_id=%r", imdb_id)
        raise HTTPException(status_code=502, detail=f"IMDB lookup failed: {exc}") from exc


@app.get("/api/overlap", response_model=OverlapResult)
async def overlap(
    ids: Annotated[
        list[str],
        Query(
            min_length=2,
            max_length=10,
            description=(
                "IMDB title ids (digits, no 'tt'). Pass two or more by repeating the "
                "query parameter: ?ids=1124373&ids=0286486&ids=0773262"
            ),
        ),
    ],
) -> OverlapResult:
    if len(set(ids)) < 2:
        raise HTTPException(
            status_code=400, detail="Please provide at least two distinct title ids."
        )
    try:
        return await asyncio.to_thread(imdb_service.overlap, ids)
    except imdb_service.TitleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("overlap failed for ids=%r", ids)
        raise HTTPException(status_code=502, detail=f"IMDB lookup failed: {exc}") from exc
