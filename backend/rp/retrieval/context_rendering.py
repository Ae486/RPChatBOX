"""Shared helpers for contextual chunk and RAG text rendering."""

from __future__ import annotations

SUMMARY_MAX_CHARS = 220
RAG_SNIPPET_MAX_CHARS = 600
IMAGE_CAPTION_MAX_CHARS = 220


def truncate_summary(summary: str | None) -> str | None:
    if summary is None:
        return None
    normalized = summary.strip()
    if not normalized:
        return None
    return normalized[:SUMMARY_MAX_CHARS]


def build_context_header(
    *,
    document_title: str | None,
    section_title: str | None,
    domain_path: str,
) -> str:
    header_parts: list[str] = []
    if document_title and document_title.strip():
        header_parts.append(document_title.strip())
    if section_title and section_title.strip():
        header_parts.append(section_title.strip())
    if domain_path.strip():
        header_parts.append(domain_path.strip())
    return " :: ".join(header_parts)


def format_page_reference(
    *,
    page_no: object | None = None,
    page_label: object | None = None,
) -> str | None:
    normalized_page_label = str(page_label or "").strip()
    if normalized_page_label:
        if page_no not in (None, "") and str(page_no).strip() != normalized_page_label:
            return f"{normalized_page_label} ({str(page_no).strip()})"
        return normalized_page_label

    if page_no in (None, ""):
        return None
    return str(page_no).strip() or None


def truncate_image_caption(image_caption: str | None) -> str | None:
    if image_caption is None:
        return None
    normalized = image_caption.strip()
    if not normalized:
        return None
    return normalized[:IMAGE_CAPTION_MAX_CHARS]


def build_context_lines(
    *,
    context_header: str | None = None,
    title: str | None = None,
    domain_path: str | None = None,
    source_ref: str | None = None,
    document_summary: str | None = None,
    page_no: object | None = None,
    page_label: object | None = None,
    image_caption: str | None = None,
    include_path: bool,
    include_source: bool,
) -> tuple[list[str], str | None]:
    header_lines: list[str] = []
    normalized_context_header = (context_header or "").strip()
    normalized_title = (title or "").strip()
    normalized_domain_path = (domain_path or "").strip()
    normalized_source_ref = (source_ref or "").strip()
    normalized_summary = truncate_summary(document_summary)
    normalized_page_ref = format_page_reference(page_no=page_no, page_label=page_label)
    normalized_image_caption = truncate_image_caption(image_caption)

    if normalized_context_header:
        header_lines.append(f"Context: {normalized_context_header}")
    elif normalized_title:
        header_lines.append(f"Title: {normalized_title}")
    if normalized_page_ref:
        header_lines.append(f"Page: {normalized_page_ref}")
    if include_path and normalized_domain_path:
        header_lines.append(f"Path: {normalized_domain_path}")
    if include_source and normalized_source_ref:
        header_lines.append(f"Source: {normalized_source_ref}")
    if normalized_summary:
        header_lines.append(f"Summary: {normalized_summary}")
    if normalized_image_caption:
        header_lines.append(f"Image: {normalized_image_caption}")
    return header_lines, normalized_summary


def build_contextual_text(
    *,
    context_header: str | None,
    document_summary: str | None,
    chunk_text: str,
    page_no: object | None = None,
    page_label: object | None = None,
    image_caption: str | None = None,
) -> str:
    header_lines, _ = build_context_lines(
        context_header=context_header,
        document_summary=document_summary,
        page_no=page_no,
        page_label=page_label,
        image_caption=image_caption,
        include_path=False,
        include_source=False,
    )
    if not header_lines:
        return chunk_text
    return "\n".join([*header_lines, chunk_text])


def build_rag_excerpt(
    *,
    context_header: str | None,
    title: str | None,
    domain_path: str | None,
    source_ref: str | None,
    document_summary: str | None,
    page_no: object | None,
    page_label: object | None,
    image_caption: str | None,
    snippet: str,
) -> tuple[str, list[str], str | None]:
    header_lines, normalized_summary = build_context_lines(
        context_header=context_header,
        title=title,
        domain_path=domain_path,
        source_ref=source_ref,
        document_summary=document_summary,
        page_no=page_no,
        page_label=page_label,
        image_caption=image_caption,
        include_path=True,
        include_source=True,
    )
    excerpt = "\n".join([*header_lines, snippet.strip()[:RAG_SNIPPET_MAX_CHARS]]).strip()
    return excerpt, header_lines, normalized_summary
