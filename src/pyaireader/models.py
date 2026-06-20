from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


FetchStrategy = Literal["auto", "http_only", "scrapling_first", "browser_first", "browser_only"]
AuthStrategy = Literal["anonymous", "user_session_fallback", "user_session_only"]
QualityLevel = Literal["strong", "usable", "weak", "failed"]

READ_RESULT_SCHEMA_VERSION = "pyaireader.read_result.v1"
INSPECT_RESULT_SCHEMA_VERSION = "pyaireader.inspect_result.v1"
BATCH_READ_RESULT_SCHEMA_VERSION = "pyaireader.batch_read_result.v1"
HEALTH_SCHEMA_VERSION = "pyaireader.health.v1"
READING_ITEM_SCHEMA_VERSION = "pyaireader.reading_item.v1"


@dataclass(frozen=True)
class ReadUrlRequest:
    url: str
    fetch_strategy: FetchStrategy = "auto"
    auth_strategy: AuthStrategy = "user_session_fallback"
    bypass_cache: bool = False
    ttl_seconds: int | None = None
    max_total_chars: int = 16000
    max_clean_text_chars: int = 12000
    max_evidence_items: int = 12
    max_number_mentions: int = 30
    max_date_mentions: int = 30
    max_entity_items: int = 40
    return_format: Literal["json", "markdown"] = "json"
    save: bool = False
    save_to: str = "default"
    project: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BatchReadUrlsRequest:
    urls: list[str]
    fetch_strategy: FetchStrategy = "auto"
    auth_strategy: AuthStrategy = "user_session_fallback"
    bypass_cache: bool = False
    max_concurrency: int = 3
    max_total_chars_per_url: int = 16000
    max_clean_text_chars_per_url: int = 12000


@dataclass(frozen=True)
class InspectUrlRequest:
    url: str
    fetch_strategy: FetchStrategy = "auto"
    auth_strategy: AuthStrategy = "anonymous"
    bypass_cache: bool = True
    html_preview_chars: int = 2000


@dataclass
class FetchAttempt:
    engine: str
    url: str
    started_at: str
    ended_at: str
    elapsed_ms: int
    status_code: int | None = None
    content_type: str | None = None
    raw_bytes_length: int = 0
    html_length: int = 0
    text_length: int = 0
    success: bool = False
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RedirectHop:
    from_url: str
    to_url: str
    status_code: int
    safety_checked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceSnippet:
    id: str
    text: str
    source_url: str
    start_char: int | None = None
    end_char: int | None = None
    reason: str | None = None
    paragraph_index: int | None = None
    signals: list[str] = field(default_factory=list)
    importance: float = 0.0
    quote_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NumberMention:
    value_raw: str
    context: str
    value_normalized: float | None = None
    unit: str | None = None
    evidence_id: str | None = None
    paragraph_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DateMention:
    date_raw: str
    context: str
    date_normalized: str | None = None
    evidence_id: str | None = None
    paragraph_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityMention:
    name: str
    entity_type: Literal["company", "industry", "product", "agency", "person", "location", "other"]
    context: str
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyMention:
    name: str
    ticker: str | None = None
    market: str | None = None
    role: str | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FinancialEvent:
    event_type: str
    confidence: float
    event_time: str | None = None
    direction: Literal["positive", "negative", "neutral", "mixed", "unknown"] = "unknown"
    source_grade: Literal["official", "major_media", "trade_media", "social", "unknown"] = "unknown"
    affected_industries: list[str] = field(default_factory=list)
    supply_chain_nodes: list[str] = field(default_factory=list)
    companies_mentioned: list[CompanyMention] = field(default_factory=list)
    impact_horizon: Literal["short", "medium", "long"] | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReaderQuality:
    score: float
    level: QualityLevel
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    subscores: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReaderTrace:
    request_id: str
    cache_hit: bool = False
    cache_key: str | None = None
    cache_policy: str | None = None
    fetch_strategy: FetchStrategy = "auto"
    fetch_engine: str | None = None
    extractor: str | None = None
    content_source: Literal["untrusted_web"] = "untrusted_web"
    content_hash: str | None = None
    raw_html_hash: str | None = None
    attempts: list[FetchAttempt] = field(default_factory=list)
    redirects: list[RedirectHop] = field(default_factory=list)
    problem_flags: list[str] = field(default_factory=list)
    auth_strategy: AuthStrategy | None = None
    user_session_used: bool = False
    browser_provider: str | None = None
    visited_urls: list[str] = field(default_factory=list)
    user_task_scope: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["attempts"] = [attempt.to_dict() for attempt in self.attempts]
        data["redirects"] = [hop.to_dict() for hop in self.redirects]
        return data


@dataclass(frozen=True)
class ReaderErrorPayload:
    code: str
    message: str
    retryable: bool
    suggested_next_action: str
    type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PlatformName = Literal["x"]
PlatformTimeRange = Literal["latest", "24h", "7d", "30d"]
PlatformFollowLinks = Literal["none", "same_platform", "same_platform_and_article_links"]


@dataclass(frozen=True)
class PlatformSearchRequest:
    platform: PlatformName
    query: str
    auth_strategy: AuthStrategy = "user_session_fallback"
    max_results: int = 30
    max_pages: int = 2
    time_range: PlatformTimeRange = "latest"
    follow_links: PlatformFollowLinks = "same_platform"


@dataclass
class PlatformEvidenceItem:
    url: str
    author: str | None = None
    published_at_raw: str | None = None
    text: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    relevance: float = 0.0
    quality: ReaderQuality | None = None
    evidence: list[EvidenceSnippet] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["quality"] = self.quality.to_dict() if self.quality else None
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@dataclass
class PlatformSearchResult:
    success: bool
    platform: str
    query: str
    items: list[PlatformEvidenceItem] = field(default_factory=list)
    trace: ReaderTrace | None = None
    error: ReaderErrorPayload | dict[str, Any] | None = None
    visited_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        data["trace"] = self.trace.to_dict() if self.trace else None
        if isinstance(self.error, ReaderErrorPayload):
            data["error"] = self.error.to_dict()
        return data


@dataclass
class FetchResult:
    url: str
    final_url: str
    fetched_at: str
    engine: str
    status_code: int | None = None
    content_type: str | None = None
    html: str | None = None
    text: str | None = None
    raw_bytes: bytes | None = None
    raw_bytes_length: int = 0
    html_length: int = 0
    text_length: int = 0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ReadUrlResult:
    success: bool
    url: str
    normalized_url: str
    fetched_at: str
    schema_version: str = READ_RESULT_SCHEMA_VERSION
    final_url: str | None = None
    domain: str | None = None
    title: str | None = None
    source: str | None = None
    author: str | None = None
    published_at_raw: str | None = None
    published_at_utc: str | None = None
    cached_at: str | None = None
    clean_text: str = ""
    summary: str | None = None
    key_points: list[str] = field(default_factory=list)
    evidence: list[EvidenceSnippet] = field(default_factory=list)
    numbers: list[NumberMention] = field(default_factory=list)
    dates: list[DateMention] = field(default_factory=list)
    entities: list[EntityMention] = field(default_factory=list)
    financial_events: list[FinancialEvent] = field(default_factory=list)
    quality: ReaderQuality | None = None
    trace: ReaderTrace | None = None
    error: ReaderErrorPayload | dict[str, Any] | None = None
    content_hash: str | None = None
    raw_html_hash: str | None = None
    saved: bool = False
    saved_item_id: str | None = None
    saved_to: str | None = None
    save_error: ReaderErrorPayload | dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        data["numbers"] = [item.to_dict() for item in self.numbers]
        data["dates"] = [item.to_dict() for item in self.dates]
        data["entities"] = [item.to_dict() for item in self.entities]
        data["financial_events"] = [item.to_dict() for item in self.financial_events]
        data["quality"] = self.quality.to_dict() if self.quality else None
        data["trace"] = self.trace.to_dict() if self.trace else None
        if isinstance(self.error, ReaderErrorPayload):
            data["error"] = self.error.to_dict()
        if isinstance(self.save_error, ReaderErrorPayload):
            data["save_error"] = self.save_error.to_dict()
        return data


@dataclass
class ReadingItem:
    id: str
    source_url: str
    final_url: str | None
    title: str | None
    author: str | None
    published_at_raw: str | None
    clean_text: str
    content_hash: str
    quality: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    project: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = READING_ITEM_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reading_item_from_read_result(
    result: ReadUrlResult,
    *,
    project: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> ReadingItem:
    if not result.success:
        raise ValueError("failed read results cannot be saved as reading items")
    if not result.clean_text.strip():
        raise ValueError("empty clean_text cannot be saved as a reading item")

    quality = result.quality.to_dict() if result.quality else {}
    trace = result.trace.to_dict() if result.trace else {}
    item_metadata = {
        "read_result_schema_version": result.schema_version,
        "normalized_url": result.normalized_url,
        "domain": result.domain,
        "source": result.source,
        "published_at_utc": result.published_at_utc,
        "result_content_hash": result.content_hash,
        "raw_html_hash": result.raw_html_hash,
        "key_points": result.key_points,
        "evidence": [item.to_dict() for item in result.evidence],
        "numbers": [item.to_dict() for item in result.numbers],
        "dates": [item.to_dict() for item in result.dates],
        "entities": [item.to_dict() for item in result.entities],
        "financial_events": [item.to_dict() for item in result.financial_events],
    }
    if metadata:
        item_metadata.update(metadata)

    content_hash = _stable_hash(result.clean_text)
    source_url = result.url
    final_url = result.final_url or result.normalized_url
    return ReadingItem(
        id=reading_item_id(source_url=source_url, final_url=final_url, content_hash=content_hash),
        source_url=source_url,
        final_url=final_url,
        title=result.title,
        author=result.author,
        published_at_raw=result.published_at_raw,
        clean_text=result.clean_text,
        content_hash=content_hash,
        quality=quality,
        trace=trace,
        metadata=item_metadata,
        tags=_dedupe_text(tags or []),
        project=project,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


def reading_item_from_dict(data: dict[str, Any]) -> ReadingItem:
    return ReadingItem(
        id=str(data["id"]),
        source_url=str(data["source_url"]),
        final_url=data.get("final_url"),
        title=data.get("title"),
        author=data.get("author"),
        published_at_raw=data.get("published_at_raw"),
        clean_text=str(data.get("clean_text", "")),
        content_hash=str(data.get("content_hash") or _stable_hash(str(data.get("clean_text", "")))),
        quality=dict(data.get("quality") or {}),
        trace=dict(data.get("trace") or {}),
        metadata=dict(data.get("metadata") or {}),
        tags=list(data.get("tags") or []),
        project=data.get("project"),
        created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        schema_version=str(data.get("schema_version") or READING_ITEM_SCHEMA_VERSION),
    )


def reading_item_id(*, source_url: str, final_url: str | None, content_hash: str) -> str:
    material = "\n".join([source_url, final_url or "", content_hash])
    return f"ri_{_stable_hash(material)[:24]}"


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dedupe_text(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output
