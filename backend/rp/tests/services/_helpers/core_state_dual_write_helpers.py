"""Test helpers for wiring Core State dual-write consumers.

S3 made write consumers fail closed when the dual-write service is absent. Tests
that bare-construct those consumers should mirror production wiring, but must not
repeat activation seeding after a test has already advanced Core revisions.
"""

from __future__ import annotations

from rp.models.dsl import Layer
from rp.services.core_state.dual_write_service import CoreStateDualWriteService
from rp.services.core_state.store_repository import CoreStateStoreRepository


def build_seeded_core_state_dual_write_service(
    retrieval_session,
    *,
    session,
    chapter,
) -> CoreStateDualWriteService:
    repository = CoreStateStoreRepository(retrieval_session)
    dual_write_service = CoreStateDualWriteService(repository=repository)
    existing_chapter_current = repository.get_authoritative_object(
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        scope="story",
        object_id="chapter.current",
    )
    if existing_chapter_current is None:
        dual_write_service.seed_activation_state(session=session, chapter=chapter)
    return dual_write_service


def build_seeded_core_state_dual_write_service_from_story_service(
    story_session_service,
    *,
    story_id: str | None = None,
    session_id: str | None = None,
) -> CoreStateDualWriteService:
    retrieval_session = getattr(story_session_service, "_session")
    # Prefer the requested session, then the story's latest, then any seeded
    # session. A test may seed extra chapter-less sessions, so skip to the first
    # session that actually has a current chapter before seeding activation.
    candidates = []
    if session_id is not None:
        candidates.append(story_session_service.get_session(session_id))
    if story_id is not None:
        candidates.append(story_session_service.get_latest_session_for_story(story_id))
    candidates.extend(story_session_service.list_sessions())
    for session in candidates:
        if session is None:
            continue
        chapter = story_session_service.get_current_chapter(session.session_id)
        if chapter is not None:
            return build_seeded_core_state_dual_write_service(
                retrieval_session,
                session=session,
                chapter=chapter,
            )
    # No seedable session+chapter resolved; the write consumers seed activation on
    # demand (apply_service._load_before_snapshot), so an unseeded service is safe.
    return CoreStateDualWriteService(
        repository=CoreStateStoreRepository(retrieval_session)
    )
