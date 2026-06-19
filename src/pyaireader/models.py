from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


FetchStrategy = Literal["auto", "http_only", "scrapling_first", "browser_first", "browser_only"]
QualityLevel = Literal["strong", "usable", "weak", "failed"]

READ_RESULT_SCHEMA_VERSION = "pyaireader.read_result.v1"
INSPECT_RESULT_SCHEMA_VERSION = "pyaireader.inspect_result.v1"
BATCH_READ_RESULT_SCHEMA_VERSION = "pyaireader.batch_read_result.v1"
HEALTH_SCHEMA_VERSION = "pyaireader.health.v1"


@dataclass(frozen=True)
class ReadUrlRequest:
    url: str
    fetch_strategy: FetchStrategy = "auto"
    bypass_cache: bool = False
    ttl_seconds: int | None = None
    max_total_chars: int = 16000
    max_clean_text_chars: int = 12000
    max_evidence_items: int = 12
    max_number_mentions: int = 30
    max_date_mentions: int = 30
    max_entity_items: int = 40
    return_format: Literal["json", "markdown"] = "json"


@dataclass(frozen=True)
class BatchReadUrlsRequest:
    urls: list[str]
    fetch_strategy: FetchStrategy = "auto"
    bypass_cache: bool = False
    max_concurrency: int = 3
    max_total_chars_per_url: int = 16000
    max_clean_text_chars_per_url: int = 12000


@dataclass(frozen=True)
class InspectUrlRequest:
    url: str
    fetch_strategy: FetchStrategy = "auto"
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
        return data
