from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pyaireader.models import (
    BATCH_READ_RESULT_SCHEMA_VERSION,
    HEALTH_SCHEMA_VERSION,
    INSPECT_RESULT_SCHEMA_VERSION,
    READ_RESULT_SCHEMA_VERSION,
    READING_ITEM_SCHEMA_VERSION,
)


class McpPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class ReaderErrorMcpPayload(McpPayload):
    code: str = ""
    message: str = ""
    retryable: bool = False
    suggested_next_action: str = ""
    type: str | None = None


class FetchAttemptMcpPayload(McpPayload):
    engine: str = ""
    url: str = ""
    started_at: str = ""
    ended_at: str = ""
    elapsed_ms: int = 0
    status_code: int | None = None
    content_type: str | None = None
    raw_bytes_length: int = 0
    html_length: int = 0
    text_length: int = 0
    success: bool = False
    error_code: str | None = None
    error_message: str | None = None


class RedirectHopMcpPayload(McpPayload):
    from_url: str = ""
    to_url: str = ""
    status_code: int = 0
    safety_checked: bool = False


class ReaderTraceMcpPayload(McpPayload):
    request_id: str = ""
    cache_hit: bool = False
    cache_key: str | None = None
    cache_policy: str | None = None
    fetch_strategy: str = "auto"
    fetch_engine: str | None = None
    extractor: str | None = None
    content_source: Literal["untrusted_web"] = "untrusted_web"
    content_hash: str | None = None
    raw_html_hash: str | None = None
    attempts: list[FetchAttemptMcpPayload] = Field(default_factory=list)
    redirects: list[RedirectHopMcpPayload] = Field(default_factory=list)
    problem_flags: list[str] = Field(default_factory=list)
    auth_strategy: str | None = None
    user_session_used: bool = False
    browser_provider: str | None = None
    visited_urls: list[str] = Field(default_factory=list)
    user_task_scope: str | None = None


class ReaderQualityMcpPayload(McpPayload):
    score: float = 0.0
    level: Literal["strong", "usable", "weak", "failed"] = "failed"
    reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    subscores: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class EvidenceSnippetMcpPayload(McpPayload):
    id: str = ""
    text: str = ""
    source_url: str = ""
    start_char: int | None = None
    end_char: int | None = None
    reason: str | None = None
    paragraph_index: int | None = None
    signals: list[str] = Field(default_factory=list)
    importance: float = 0.0
    quote_hash: str | None = None


class NumberMentionMcpPayload(McpPayload):
    value_raw: str = ""
    context: str = ""
    value_normalized: float | None = None
    unit: str | None = None
    evidence_id: str | None = None
    paragraph_index: int | None = None


class DateMentionMcpPayload(McpPayload):
    date_raw: str = ""
    context: str = ""
    date_normalized: str | None = None
    evidence_id: str | None = None
    paragraph_index: int | None = None


class EntityMentionMcpPayload(McpPayload):
    name: str = ""
    entity_type: Literal[
        "company",
        "industry",
        "product",
        "agency",
        "person",
        "location",
        "other",
    ] = "other"
    context: str = ""
    evidence_id: str | None = None


class CompanyMentionMcpPayload(McpPayload):
    name: str = ""
    ticker: str | None = None
    market: str | None = None
    role: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class FinancialEventMcpPayload(McpPayload):
    event_type: str = ""
    confidence: float = 0.0
    event_time: str | None = None
    direction: Literal["positive", "negative", "neutral", "mixed", "unknown"] = "unknown"
    source_grade: Literal["official", "major_media", "trade_media", "social", "unknown"] = "unknown"
    affected_industries: list[str] = Field(default_factory=list)
    supply_chain_nodes: list[str] = Field(default_factory=list)
    companies_mentioned: list[CompanyMentionMcpPayload] = Field(default_factory=list)
    impact_horizon: Literal["short", "medium", "long"] | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ReadingItemMcpPayload(McpPayload):
    id: str = ""
    source_url: str = ""
    final_url: str | None = None
    title: str | None = None
    author: str | None = None
    published_at_raw: str | None = None
    clean_text: str = ""
    content_hash: str = ""
    quality: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    project: str | None = None
    created_at: str = ""
    schema_version: str = READING_ITEM_SCHEMA_VERSION


class ReadingItemSummaryMcpPayload(McpPayload):
    id: str = ""
    source_url: str = ""
    final_url: str | None = None
    title: str | None = None
    author: str | None = None
    published_at_raw: str | None = None
    content_hash: str = ""
    quality: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    project: str | None = None
    created_at: str = ""
    schema_version: str = READING_ITEM_SCHEMA_VERSION
    clean_text_length: int = 0
    clean_text_preview: str = ""


class ReadUrlMcpResult(McpPayload):
    success: bool
    url: str = ""
    normalized_url: str = ""
    fetched_at: str = ""
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
    key_points: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSnippetMcpPayload] = Field(default_factory=list)
    numbers: list[NumberMentionMcpPayload] = Field(default_factory=list)
    dates: list[DateMentionMcpPayload] = Field(default_factory=list)
    entities: list[EntityMentionMcpPayload] = Field(default_factory=list)
    financial_events: list[FinancialEventMcpPayload] = Field(default_factory=list)
    quality: ReaderQualityMcpPayload | None = None
    trace: ReaderTraceMcpPayload | None = None
    error: ReaderErrorMcpPayload | None = None
    content_hash: str | None = None
    raw_html_hash: str | None = None
    saved: bool = False
    saved_item_id: str | None = None
    saved_to: str | None = None
    save_error: ReaderErrorMcpPayload | None = None


class BatchReadUrlsMcpResult(McpPayload):
    success: bool
    schema_version: str = BATCH_READ_RESULT_SCHEMA_VERSION
    count: int = 0
    success_count: int = 0
    results: list[ReadUrlMcpResult] = Field(default_factory=list)
    error: ReaderErrorMcpPayload | None = None


class InspectUrlMcpResult(McpPayload):
    success: bool
    schema_version: str = INSPECT_RESULT_SCHEMA_VERSION
    url: str = ""
    normalized_url: str | None = None
    final_url: str | None = None
    domain: str | None = None
    title: str | None = None
    fetched_at: str = ""
    status_code: int | None = None
    content_type: str | None = None
    raw_bytes_length: int = 0
    html_length: int = 0
    text_length: int = 0
    html_preview: str = ""
    quality: ReaderQualityMcpPayload | None = None
    trace: ReaderTraceMcpPayload | None = None
    error: ReaderErrorMcpPayload | None = None


class ClearCacheMcpResult(McpPayload):
    success: bool
    deleted: int = 0
    error: ReaderErrorMcpPayload | None = None


class StorageStatusMcpResult(McpPayload):
    success: bool
    config_path: str = ""
    loaded_from_file: bool = False
    default_store: str = "default"
    stores: list[dict[str, Any]] = Field(default_factory=list)
    reserved_drivers: list[str] = Field(default_factory=list)
    error: ReaderErrorMcpPayload | None = None


class SaveReadingItemMcpResult(McpPayload):
    success: bool
    store: str = "default"
    item_id: str = ""
    created: bool = False
    item: ReadingItemMcpPayload | None = None
    error: ReaderErrorMcpPayload | str | None = None


class LibraryListMcpResult(McpPayload):
    success: bool
    store: str = "default"
    count: int = 0
    items: list[ReadingItemSummaryMcpPayload | ReadingItemMcpPayload] = Field(default_factory=list)
    error: ReaderErrorMcpPayload | None = None


class LibraryGetMcpResult(McpPayload):
    success: bool
    store: str = "default"
    item_id: str = ""
    item: ReadingItemMcpPayload | None = None
    error: ReaderErrorMcpPayload | None = None


class LibrarySearchMcpResult(McpPayload):
    success: bool
    store: str = "default"
    query: str = ""
    count: int = 0
    items: list[ReadingItemSummaryMcpPayload | ReadingItemMcpPayload] = Field(default_factory=list)
    error: ReaderErrorMcpPayload | None = None


class BrowserSessionStatusMcpResult(McpPayload):
    success: bool
    provider_mode: str = "auto"
    active_provider: str | None = None
    available: bool = False
    cdp_endpoint: str | None = None
    profile_dir: str = ""
    providers: list[dict[str, Any]] = Field(default_factory=list)
    note: str = ""
    error: ReaderErrorMcpPayload | None = None


class PlatformEvidenceItemMcpPayload(McpPayload):
    url: str = ""
    author: str | None = None
    published_at_raw: str | None = None
    text: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    relevance: float = 0.0
    quality: ReaderQualityMcpPayload | None = None
    evidence: list[EvidenceSnippetMcpPayload] = Field(default_factory=list)


class PlatformSearchMcpResult(McpPayload):
    success: bool
    platform: str = ""
    query: str = ""
    items: list[PlatformEvidenceItemMcpPayload] = Field(default_factory=list)
    trace: ReaderTraceMcpPayload | None = None
    error: ReaderErrorMcpPayload | None = None
    visited_urls: list[str] = Field(default_factory=list)


class ReaderHealthMcpResult(McpPayload):
    success: bool
    schema_version: str = HEALTH_SCHEMA_VERSION
    name: str = "pyaireader"
    version: str = ""
    transport: Literal["stdio", "streamable-http"] = "stdio"
    content_source: Literal["untrusted_web"] = "untrusted_web"
    tools: list[str] = Field(default_factory=list)
    schemas: dict[str, str] = Field(default_factory=dict)
    fetch_strategies: list[str] = Field(default_factory=list)
    auth_strategies: list[str] = Field(default_factory=list)
    return_formats: list[str] = Field(default_factory=list)
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    cache_path: str = ""
    safety: dict[str, Any] = Field(default_factory=dict)
    mcp_http: dict[str, Any] | None = None
    error: ReaderErrorMcpPayload | None = None
