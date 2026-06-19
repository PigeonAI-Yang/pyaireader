from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pyaireader.cache import SQLiteReaderCache
from pyaireader.cache.sqlite_cache import CacheWritePolicy
from pyaireader.config import ReaderConfig
from pyaireader.errors import ExtractionError, FetchError, ReaderError, UnsafeUrlError
from pyaireader.extractors import ExtractedText, PdfExtractor, TextExtractor
from pyaireader.fetchers import FetchResponse, HttpFetcher, PlaywrightFetcher, ScraplingFetcher
from pyaireader.finance import extract_financial_events
from pyaireader.models import (
    BATCH_READ_RESULT_SCHEMA_VERSION,
    BatchReadUrlsRequest,
    CompanyMention,
    DateMention,
    EntityMention,
    EvidenceSnippet,
    FetchAttempt,
    FinancialEvent,
    INSPECT_RESULT_SCHEMA_VERSION,
    InspectUrlRequest,
    NumberMention,
    READ_RESULT_SCHEMA_VERSION,
    ReadUrlRequest,
    ReadUrlResult,
    ReaderErrorPayload,
    ReaderQuality,
    ReaderTrace,
)
from pyaireader.processors import (
    extract_dates,
    extract_entities,
    extract_numbers,
    pick_evidence,
    split_paragraphs,
)
from pyaireader.quality import score_quality
from pyaireader.reader.normalizer import extract_domain, normalize_url
from pyaireader.reader.safety import assert_url_safe
from pyaireader.reader.traces import sha256_text


class ReaderPipeline:
    def __init__(
        self,
        config: ReaderConfig | None = None,
        fetcher: HttpFetcher | None = None,
        scrapling_fetcher: ScraplingFetcher | None = None,
        browser_fetcher: PlaywrightFetcher | None = None,
        extractor: TextExtractor | None = None,
        pdf_extractor: PdfExtractor | None = None,
        cache: SQLiteReaderCache | None = None,
    ) -> None:
        self.config = config or ReaderConfig.default()
        self.fetcher = fetcher or HttpFetcher(
            timeout_seconds=self.config.fetch_timeout_seconds,
            max_redirects=self.config.max_redirects,
        )
        self.scrapling_fetcher = scrapling_fetcher or ScraplingFetcher(mode="static")
        self.scrapling_stealth_fetcher = ScraplingFetcher(mode="stealth")
        self.scrapling_dynamic_fetcher = ScraplingFetcher(mode="dynamic")
        self.browser_fetcher = browser_fetcher or PlaywrightFetcher(
            timeout_ms=int(self.config.fetch_timeout_seconds * 1000)
        )
        self.extractor = extractor or TextExtractor()
        self.pdf_extractor = pdf_extractor or PdfExtractor()
        self.cache = cache or SQLiteReaderCache(self.config.cache_path)

    @classmethod
    def from_default(cls) -> "ReaderPipeline":
        return cls()

    @classmethod
    def from_env(cls) -> "ReaderPipeline":
        return cls(config=ReaderConfig.from_env())

    def read(self, request: ReadUrlRequest) -> ReadUrlResult:
        fetched_at = _now_iso()
        trace = ReaderTrace(request_id=str(uuid4()), fetch_strategy=request.fetch_strategy)
        try:
            normalized_url = normalize_url(request.url)
            assert_url_safe(normalized_url)
            trace.cache_key = self._cache_key(normalized_url, request)

            if not request.bypass_cache:
                cached = self.cache.get(trace.cache_key)
                if cached:
                    result = _result_from_dict(cached)
                    if result.trace:
                        result.trace.cache_hit = True
                    return result

            response = self._fetch_with_strategy(request, normalized_url, trace)
            trace.raw_html_hash = sha256_text(response.raw)
            trace.redirects.extend(response.redirects)

            extracted = self._extract_response(response)
            trace.extractor = extracted.extractor
            trace.content_source = "untrusted_web"
            trace.content_hash = sha256_text(extracted.clean_text)  # type: ignore[attr-defined]
            trace.attempts.append(
                FetchAttempt(
                    engine=extracted.extractor,
                    url=response.final_url,
                    started_at=fetched_at,
                    ended_at=_now_iso(),
                    elapsed_ms=0,
                    text_length=len(extracted.clean_text),
                    success=True,
                )
            )

            paragraphs = split_paragraphs(extracted.clean_text)
            evidence = pick_evidence(
                paragraphs,
                max_items=request.max_evidence_items,
                source_url=response.final_url,
                preferred_text=extracted.primary_text,
                preferred_reason=extracted.extractor if extracted.extractor == "x_status" else None,
            )
            numbers = extract_numbers(paragraphs, evidence, limit=request.max_number_mentions)
            dates = extract_dates(paragraphs, evidence, limit=request.max_date_mentions)
            entities = extract_entities(paragraphs, evidence, limit=request.max_entity_items)
            financial_events = extract_financial_events(evidence, entities)
            quality = score_quality(
                response.text,
                extracted.clean_text,
                extracted.title,
                len(evidence),
                extractor=extracted.extractor,
            )
            trace.problem_flags = quality.flags

            clean_text = _truncate(extracted.clean_text, request.max_clean_text_chars)
            result = ReadUrlResult(
                success=True,
                url=request.url,
                normalized_url=normalized_url,
                final_url=response.final_url,
                domain=extract_domain(response.final_url),
                title=extracted.title,
                source=extracted.source,
                author=extracted.author,
                published_at_raw=extracted.published_at_raw,
                published_at_utc=extracted.published_at_utc,
                fetched_at=fetched_at,
                clean_text=clean_text,
                summary=None,
                key_points=_build_key_points(evidence),
                evidence=evidence,
                numbers=numbers,
                dates=dates,
                entities=entities,
                financial_events=financial_events,
                quality=quality,
                trace=trace,
                content_hash=sha256_text(extracted.clean_text),
                raw_html_hash=sha256_text(response.raw),
            )

            policy = self._cache_policy(result, response)
            trace.cache_policy = policy.name
            if policy.should_write and trace.cache_key:
                self.cache.set(
                    trace.cache_key,
                    normalized_url,
                    result.to_dict(),
                    ttl_seconds=policy.ttl_seconds,
                    cache_policy=policy.name,
                )
            return result
        except ReaderError as exc:
            return self._error_result(request.url, request.url, fetched_at, trace, exc)
        except Exception as exc:
            return self._error_result(request.url, request.url, fetched_at, trace, exc)

    def batch_read(self, request: BatchReadUrlsRequest | list[ReadUrlRequest]) -> dict[str, Any]:
        if isinstance(request, list):
            requests = request
        else:
            requests = [
                ReadUrlRequest(
                    url=url,
                    fetch_strategy=request.fetch_strategy,
                    bypass_cache=request.bypass_cache,
                    max_total_chars=request.max_total_chars_per_url,
                    max_clean_text_chars=request.max_clean_text_chars_per_url,
                )
                for url in request.urls
            ]
        results = [self.read(item).to_dict() for item in requests]
        return {
            "schema_version": BATCH_READ_RESULT_SCHEMA_VERSION,
            "success": True,
            "count": len(results),
            "success_count": sum(1 for result in results if result.get("success")),
            "results": results,
        }

    def inspect(self, request: InspectUrlRequest | ReadUrlRequest) -> dict[str, Any]:
        inspect_request = (
            request
            if isinstance(request, InspectUrlRequest)
            else InspectUrlRequest(url=request.url, fetch_strategy=request.fetch_strategy)
        )
        trace = ReaderTrace(request_id=str(uuid4()), fetch_strategy=inspect_request.fetch_strategy)
        fetched_at = _now_iso()
        try:
            normalized_url = normalize_url(inspect_request.url)
            assert_url_safe(normalized_url)
            response = self._fetch_with_strategy(
                ReadUrlRequest(url=normalized_url, fetch_strategy=inspect_request.fetch_strategy),
                normalized_url,
                trace,
            )
            trace.fetch_engine = response.headers.get("x-pyaireader-engine", self.fetcher.name)
            trace.redirects.extend(response.redirects)
            trace.raw_html_hash = sha256_text(response.raw)
            extracted = self._extract_response(response)
            quality = score_quality(
                response.text,
                extracted.clean_text,
                extracted.title,
                0,
                extractor=extracted.extractor,
            )
            trace.extractor = extracted.extractor
            trace.problem_flags = quality.flags
            return {
                "schema_version": INSPECT_RESULT_SCHEMA_VERSION,
                "success": True,
                "url": inspect_request.url,
                "normalized_url": normalized_url,
                "final_url": response.final_url,
                "domain": extract_domain(response.final_url),
                "title": extracted.title,
                "fetched_at": fetched_at,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "raw_bytes_length": response.raw_bytes_length,
                "html_length": response.html_length,
                "text_length": len(extracted.clean_text),
                "html_preview": response.text[: inspect_request.html_preview_chars],
                "quality": quality.to_dict(),
                "trace": trace.to_dict(),
                "error": None,
            }
        except Exception as exc:
            trace.problem_flags.append(_error_code(exc))
            return {
                "schema_version": INSPECT_RESULT_SCHEMA_VERSION,
                "success": False,
                "url": inspect_request.url,
                "fetched_at": fetched_at,
                "quality": score_quality("", "", None, 0).to_dict(),
                "trace": trace.to_dict(),
                "error": _reader_error_payload(exc).to_dict(),
            }

    def clear_cache(self, url: str | None = None, domain: str | None = None) -> dict[str, Any]:
        normalized = normalize_url(url) if url else None
        deleted = self.cache.clear(normalized, domain)
        return {"success": True, "deleted": deleted}

    def _fetch_with_strategy(
        self,
        request: ReadUrlRequest,
        normalized_url: str,
        trace: ReaderTrace,
    ) -> FetchResponse:
        errors: list[str] = []
        for engine_name, fetcher in self._fetch_plan(request):
            try:
                response = fetcher.fetch(normalized_url)
                trace.fetch_engine = response.headers.get("x-pyaireader-engine", engine_name)
                trace.attempts.append(_fetch_attempt(response, success=True, engine_name=engine_name))
                if self._response_needs_fallback(response) and self._has_next_engine(
                    request, engine_name
                ):
                    errors.append(f"{engine_name}: weak response")
                    continue
                return response
            except Exception as exc:
                errors.append(f"{engine_name}: {exc}")
                trace.attempts.append(_error_attempt(engine_name, normalized_url, exc))
                continue
        raise ReaderError("; ".join(errors) or f"no fetcher available for {request.fetch_strategy}")

    def _fetch_plan(self, request: ReadUrlRequest) -> list[tuple[str, Any]]:
        http = [(getattr(self.fetcher, "name", "http"), self.fetcher)]
        scrapling = [
            (f"{getattr(self.scrapling_fetcher, 'name', 'scrapling')}:static", self.scrapling_fetcher),
            ("scrapling:stealth", self.scrapling_stealth_fetcher),
            ("scrapling:dynamic", self.scrapling_dynamic_fetcher),
        ]
        browser = [(getattr(self.browser_fetcher, "name", "raw_browser"), self.browser_fetcher)]
        if request.fetch_strategy == "http_only":
            return http
        if request.fetch_strategy == "scrapling_first":
            return scrapling + browser
        if request.fetch_strategy == "browser_first":
            return browser + http
        if request.fetch_strategy == "browser_only":
            return browser
        return http + scrapling + browser

    def _has_next_engine(self, request: ReadUrlRequest, engine_name: str) -> bool:
        plan = self._fetch_plan(request)
        names = [name for name, _ in plan]
        return engine_name in names and names.index(engine_name) < len(names) - 1

    def _response_needs_fallback(self, response: FetchResponse) -> bool:
        html_len = len(response.text or "")
        if response.status_code in {403, 429}:
            return True
        if html_len < 80 and response.raw_bytes_length > 1000:
            return True
        lowered = (response.text or "").lower()
        return any(marker in lowered for marker in ["id=\"root\"", "id=\"app\"", "__next_data__"])

    def _extract_response(self, response: FetchResponse):
        content_type = (response.content_type or "").lower()
        is_pdf = "application/pdf" in content_type or response.final_url.lower().endswith(".pdf")
        if is_pdf:
            text = self.pdf_extractor.extract_bytes(response.raw or b"")
            return ExtractedText(title=None, clean_text=text, extractor="pdf")
        return self.extractor.extract(response.text, url=response.final_url)

    def _cache_key(self, normalized_url: str, request: ReadUrlRequest) -> str:
        material = "|".join(
            [
                normalized_url,
                request.fetch_strategy,
                request.return_format,
                str(_bucket(request.max_clean_text_chars)),
                str(request.max_evidence_items),
                str(request.max_number_mentions),
                str(request.max_date_mentions),
                str(request.max_entity_items),
                "extractor:v1",
            ]
        )
        return sha256_text(material) or normalized_url

    def _cache_policy(self, result: ReadUrlResult, response: FetchResponse) -> CacheWritePolicy:
        if not result.success:
            return CacheWritePolicy("failure_no_cache", False)
        if response.status_code == 404:
            return CacheWritePolicy("not_found", True, self.config.not_found_ttl_seconds)
        if response.status_code in {403, 429}:
            return CacheWritePolicy("diagnostic", True, self.config.diagnostic_ttl_seconds)
        if result.quality and result.quality.level == "weak":
            return CacheWritePolicy("weak", True, self.config.weak_ttl_seconds)
        if result.quality and result.quality.level == "failed":
            return CacheWritePolicy("failed_diagnostic", True, self.config.diagnostic_ttl_seconds)
        return CacheWritePolicy("positive", True, self.config.cache_ttl_seconds)

    def _error_result(
        self,
        url: str,
        normalized_url: str,
        fetched_at: str,
        trace: ReaderTrace,
        exc: Exception,
    ) -> ReadUrlResult:
        message = str(exc)
        trace.problem_flags.append(_error_code(exc))
        return ReadUrlResult(
            success=False,
            url=url,
            normalized_url=normalized_url,
            fetched_at=fetched_at,
            clean_text="",
            summary=None,
            key_points=[],
            quality=score_quality("", "", None, 0),
            trace=trace,
            error=_reader_error_payload(exc, message=message),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, char_limit: int) -> str:
    if len(text) <= char_limit:
        return text
    return text[:char_limit].rstrip()


def _bucket(value: int) -> int:
    return int(value / 1000) * 1000


def _build_key_points(evidence: list[EvidenceSnippet], limit: int = 5) -> list[str]:
    return [_truncate(item.text, 160) for item in evidence[:limit]]


def _fetch_attempt(
    response: FetchResponse,
    *,
    success: bool,
    engine_name: str | None = None,
) -> FetchAttempt:
    ended_at = _now_iso()
    return FetchAttempt(
        engine=response.headers.get("x-pyaireader-engine", engine_name or "http"),
        url=response.final_url,
        started_at=ended_at,
        ended_at=ended_at,
        elapsed_ms=response.elapsed_ms,
        status_code=response.status_code,
        content_type=response.content_type,
        raw_bytes_length=response.raw_bytes_length,
        html_length=response.html_length,
        text_length=response.text_length,
        success=success,
    )


def _error_attempt(engine_name: str, url: str, exc: Exception) -> FetchAttempt:
    ended_at = _now_iso()
    return FetchAttempt(
        engine=engine_name,
        url=url,
        started_at=ended_at,
        ended_at=ended_at,
        elapsed_ms=0,
        success=False,
        error_code=_error_code(exc),
        error_message=str(exc),
    )


def _error_code(exc: Exception) -> str:
    if isinstance(exc, UnsafeUrlError):
        return "unsafe_url"
    if isinstance(exc, FetchError):
        return "fetch_failed"
    if isinstance(exc, ExtractionError):
        return "extraction_failed"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ValueError):
        return "invalid_request"
    name = exc.__class__.__name__.lower()
    if isinstance(exc, ReaderError) and str(exc).startswith("fetch_strategy not implemented"):
        return "not_implemented"
    if isinstance(exc, ReaderError):
        return "fetch_failed"
    return name


def _reader_error_payload(exc: Exception, *, message: str | None = None) -> ReaderErrorPayload:
    code = _error_code(exc)
    return ReaderErrorPayload(
        code=code,
        message=message if message is not None else str(exc),
        retryable=_error_retryable(code),
        suggested_next_action=_suggested_next_action(code),
        type=exc.__class__.__name__,
    )


def _error_retryable(code: str) -> bool:
    return code in {
        "fetch_failed",
        "timeout",
        "extraction_failed",
        "httpstatuserror",
        "connecterror",
        "readtimeout",
    }


def _suggested_next_action(code: str) -> str:
    if code == "unsafe_url":
        return "use_public_http_or_https_url"
    if code == "invalid_request":
        return "fix_request_parameters"
    if code == "timeout":
        return "retry_with_longer_timeout_or_lighter_strategy"
    if code in {"fetch_failed", "httpstatuserror", "connecterror", "readtimeout"}:
        return "retry_with_scrapling_first_or_inspect_url"
    if code == "extraction_failed":
        return "inspect_url_or_retry_with_browser_only"
    if code == "not_implemented":
        return "choose_supported_fetch_strategy"
    return "inspect_url"


def _result_from_dict(data: dict[str, Any]) -> ReadUrlResult:
    trace_data = data.get("trace") or {}
    trace = ReaderTrace(
        request_id=trace_data.get("request_id", str(uuid4())),
        cache_hit=trace_data.get("cache_hit", False),
        cache_key=trace_data.get("cache_key"),
        cache_policy=trace_data.get("cache_policy"),
        fetch_strategy=trace_data.get("fetch_strategy", "auto"),
        fetch_engine=trace_data.get("fetch_engine"),
        extractor=trace_data.get("extractor"),
        content_source=trace_data.get("content_source", "untrusted_web"),
        attempts=[FetchAttempt(**item) for item in trace_data.get("attempts", [])],
        problem_flags=trace_data.get("problem_flags", []),
    )
    quality_data = data.get("quality") or {}
    quality = ReaderQuality(**quality_data) if quality_data else None
    return ReadUrlResult(
        success=data["success"],
        url=data["url"],
        normalized_url=data.get("normalized_url", data["url"]),
        fetched_at=data["fetched_at"],
        schema_version=data.get("schema_version", READ_RESULT_SCHEMA_VERSION),
        final_url=data.get("final_url"),
        domain=data.get("domain"),
        title=data.get("title"),
        source=data.get("source"),
        author=data.get("author"),
        published_at_raw=data.get("published_at_raw"),
        published_at_utc=data.get("published_at_utc"),
        cached_at=data.get("cached_at"),
        clean_text=data.get("clean_text", ""),
        summary=data.get("summary"),
        key_points=data.get("key_points", []),
        evidence=[EvidenceSnippet(**item) for item in data.get("evidence", [])],
        numbers=[NumberMention(**item) for item in data.get("numbers", [])],
        dates=[DateMention(**item) for item in data.get("dates", [])],
        entities=[EntityMention(**item) for item in data.get("entities", [])],
        financial_events=[
            FinancialEvent(
                **{
                    **item,
                    "companies_mentioned": [
                        CompanyMention(**company)
                        for company in item.get("companies_mentioned", [])
                    ],
                }
            )
            for item in data.get("financial_events", [])
        ],
        quality=quality,
        trace=trace,
        error=data.get("error"),
        content_hash=data.get("content_hash"),
        raw_html_hash=data.get("raw_html_hash"),
    )
