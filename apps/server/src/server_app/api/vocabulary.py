"""Per-user custom vocabulary (boost terms + mishear corrections).

Applied automatically to every transcription the user submits — see
``build_vocabulary`` and its use in the jobs API.
"""

from __future__ import annotations

from typing import Annotated

from engine.config import CorrectionRule
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from server_app.auth.deps import CurrentUser, get_db
from server_app.models import VocabularyEntry
from server_app.schemas import VocabularyEntryCreate, VocabularyEntryOut

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])


def _to_out(entry: VocabularyEntry) -> VocabularyEntryOut:
    return VocabularyEntryOut(
        id=entry.id, term=entry.term, variants=entry.variants, created_at=entry.created_at
    )


@router.get("")
def list_vocabulary(
    user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> list[VocabularyEntryOut]:
    entries = (
        db.execute(
            select(VocabularyEntry)
            .where(VocabularyEntry.user_id == user.id)
            .order_by(VocabularyEntry.term)
        )
        .scalars()
        .all()
    )
    return [_to_out(e) for e in entries]


@router.post("", status_code=201)
def create_vocabulary(
    body: VocabularyEntryCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> VocabularyEntryOut:
    term = body.term.strip()
    if not term:
        raise HTTPException(status_code=422, detail="Begriff darf nicht leer sein")
    existing = db.execute(
        select(VocabularyEntry).where(
            VocabularyEntry.user_id == user.id, VocabularyEntry.term == term
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.variants = body.variants.strip()
        db.flush()
        return _to_out(existing)
    entry = VocabularyEntry(user_id=user.id, term=term, variants=body.variants.strip())
    db.add(entry)
    db.flush()
    return _to_out(entry)


@router.delete("/{entry_id}", status_code=204)
def delete_vocabulary(
    entry_id: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> Response:
    entry = db.execute(
        select(VocabularyEntry).where(
            VocabularyEntry.id == entry_id, VocabularyEntry.user_id == user.id
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    db.delete(entry)
    return Response(status_code=204)


def build_vocabulary(db: Session, user_id: str) -> tuple[str, list[CorrectionRule]]:
    """Return (boost string, corrections) assembled from a user's dictionary.

    * every term is a hotword boost;
    * every variant becomes a correction ``variant`` → ``term``.
    """
    entries = (
        db.execute(select(VocabularyEntry).where(VocabularyEntry.user_id == user_id))
        .scalars()
        .all()
    )
    boost_terms: list[str] = []
    corrections: list[CorrectionRule] = []
    for entry in entries:
        boost_terms.append(entry.term)
        for variant in entry.variant_list():
            corrections.append(CorrectionRule(wrong=variant, right=entry.term))
    return " ".join(boost_terms), corrections
