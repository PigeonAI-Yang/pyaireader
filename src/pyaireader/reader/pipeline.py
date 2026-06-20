from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pyaireader.cache import SQLiteReaderCache
from pyaireader.cache.sqlite_cache import CacheWritePolicy
from pyaireader.browser_sessions import BrowserSessionFetcher
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
    ReadingItem,
    RedirectHop,
    PlatformSearchRequest,
    PlatformSearchResult,
    ReadUrlRequest,
    ReadUrlResult,
    ReaderErrorPayload,
    ReaderQuality,
    ReaderTrace,
    reading_item_from_read_result,
)
from pyaireader.platforms import get_platform_reader
from pyaireader.platforms.base import PlatformContext
from pyaireader.platforms.x.search_reader import XSearchReader
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
from pyaireader.storage import StorageManager


class ReaderPipeline:
    def __init__(
        self,
        config: ReaderConfig | None = None,
        fetcher: HttpFetcher | None = None,
        scrapling_fetcher: ScraplingFetcher | None = None,
        browser_fetcher: PlaywrightFetcher | None = None,
        browser_session_fetcher: BrowserSessionFetcher | None = None,
        extractor: TextExtractor | None = None,
        pdf_extractor: PdfExtractor | None = None,
        cache: SQLiteReaderCache | None = None,
        storage_manager: StorageManager | None = None,
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
        self.browser_session_fetcher = browser_session_fetcher or BrowserSessionFetcher(
            timeout_ms=int(self.config.fetch_timeout_seconds * 1000)
        )
        self.extractor = extractor or TextExtractor()
        self.pdf_extractor = pdf_extractor or PdfExtractor()
        self.cache = cache or SQLiteReaderCache(self.config.cache_path)
        self._storage_manager = storage_manager

    @classmethod
    def from_default(cls) -> "ReaderPipeline":
        return cls()

    @classmethod
    def from_env(cls) -> "ReaderPipeline":
        return cls(config=ReaderConfig.from_env())

    def read(self, request: ReadUrlRequest) -> ReadUrlResult:
        fetched_at = _now_iso()
        trace = ReaderTrace(
            request_id=str(uuid4()),
            fetch_strategy=request.fetch_strategy,
            auth_strategy=request.auth_strategy,
        )
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
                    return self._save_result_if_requested(request, result)

            platform_result = self._read_with_platform(request, normalized_url, fetched_at, trace)
            if platform_result:
                self._write_result_cache(normalized_url, platform_result, None)
                return self._save_result_if_requested(request, platform_result)

            response = self._fetch_with_strategy(request, normalized_url, trace)
            trace.redirects.extend(response.redirects)

            extracted = self._extract_response(response)
            result = self._build_success_result(
                request,
                normalized_url,
                fetched_at,
                trace,
                response,
                extracted,
            )
            self._write_result_cache(normalized_url, result, response)
            return self._save_result_if_requested(request, result)
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
                    auth_strategy=request.auth_strategy,
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
        trace = ReaderTrace(
            request_id=str(uuid4()),
            fetch_strategy=inspect_request.fetch_strategy,
            auth_strategy=inspect_request.auth_strategy,
        )
        fetched_at = _now_iso()
        try:
            normalized_url = normalize_url(inspect_request.url)
            assert_url_safe(normalized_url)
            response = self._fetch_with_strategy(
                ReadUrlRequest(
                    url=normalized_url,
                    fetch_strategy=inspect_request.fetch_strategy,
                    auth_strategy=inspect_request.auth_strategy,
                ),
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

    def storage_status(self) -> dict[str, Any]:
        return self._get_storage_manager().status()

    def save_reading_item(
        self,
        item: ReadingItem | dict[str, Any],
        *,
        store: str = "default",
    ) -> dict[str, Any]:
        return self._get_storage_manager().save(item, store=store).to_dict()

    def library_get(self, item_id: str, *, store: str = "default") -> dict[str, Any]:
        return self._get_storage_manager().get(item_id, store=store)

    def library_list(
        self,
        *,
        store: str = "default",
        limit: int = 20,
        offset: int = 0,
        project: str | None = None,
        include_text: bool = False,
    ) -> dict[str, Any]:
        return self._get_storage_manager().list(
            store=store,
            limit=limit,
            offset=offset,
            project=project,
            include_text=include_text,
        )

    def library_search(
        self,
        query: str,
        *,
        store: str = "default",
        limit: int = 20,
        project: str | None = None,
        include_text: bool = False,
    ) -> dict[str, Any]:
        return self._get_storage_manager().search(
            query,
            store=store,
            limit=limit,
            project=project,
            include_text=include_text,
        )

    def library_export(
        self,
        item_id: str,
        *,
        store: str = "default",
        format: str = "json",
    ) -> dict[str, Any]:
        return self._get_storage_manager().export(item_id, store=store, format=format)

    def search_platform(self, request: PlatformSearchRequest) -> PlatformSearchResult:
        trace = ReaderTrace(
            request_id=str(uuid4()),
            fetch_strategy="auto",
            auth_strategy=request.auth_strategy,
            user_task_scope=f"{request.platform}_search",
        )
        try:
            _validate_platform_search_request(request)
            if request.platform == "x":
                return XSearchReader().search(
                    request,
                    trace,
                    fetch_user_session_url=lambda url, task_scope=None: (
                        self._platform_user_session_fetch(url, trace, task_scope=task_scope)
                    ),
                    fetch_anonymous_url=lambda url: self._platform_fetch(url, trace),
                )
            return _platform_search_error(
                request,
                trace,
                "unsupported_platform",
                f"unsupported platform: {request.platform}",
                retryable=False,
                suggested_next_action="choose_supported_platform",
            )
        except Exception as exc:
            code = _error_code(exc)
            trace.problem_flags = _dedupe_list([*trace.problem_flags, code])
            return _platform_search_error(
                request,
                trace,
                code,
                str(exc),
                retryable=_error_retryable(code),
                suggested_next_action=_suggested_next_action(code),
                error_type=exc.__class__.__name__,
            )

    def _read_with_platform(
        self,
        request: ReadUrlRequest,
        normalized_url: str,
        fetched_at: str,
        trace: ReaderTrace,
    ) -> ReadUrlResult | None:
        reader = get_platform_reader(normalized_url)
        if not reader:
            return None
        context = PlatformContext(
            request=request,
            normalized_url=normalized_url,
            fetched_at=fetched_at,
            trace=trace,
            fetch_url=lambda url: self._platform_fetch(url, trace),
            fetch_user_session_url=lambda url, task_scope=None: self._platform_user_session_fetch(
                url,
                trace,
                task_scope=task_scope,
            ),
            build_success_result=lambda response, extracted: self._build_success_result(
                request,
                normalized_url,
                fetched_at,
                trace,
                response,
                extracted,
            ),
            build_failure_result=lambda final_url, extractor, code, flags, message, action: (
                self._build_platform_failure_result(
                    request,
                    normalized_url,
                    fetched_at,
                    trace,
                    final_url,
                    extractor,
                    code,
                    flags,
                    message,
                    action,
                )
            ),
        )
        return reader.read(context)

    def _platform_fetch(self, url: str, trace: ReaderTrace) -> FetchResponse:
        try:
            response = self.fetcher.fetch(url)
            engine_name = response.headers.get("x-pyaireader-engine", getattr(self.fetcher, "name", "http"))
            trace.fetch_engine = engine_name
            trace.attempts.append(_fetch_attempt(response, success=True, engine_name=engine_name))
            trace.redirects.extend(response.redirects)
            return response
        except Exception as exc:
            trace.attempts.append(_error_attempt(getattr(self.fetcher, "name", "http"), url, exc))
            raise

    def _platform_user_session_fetch(
        self,
        url: str,
        trace: ReaderTrace,
        *,
        task_scope: str | None = None,
    ) -> FetchResponse:
        try:
            response = self.browser_session_fetcher.fetch(url, task_scope=task_scope)
            engine_name = response.headers.get("x-pyaireader-engine", "authenticated_browser")
            trace.fetch_engine = engine_name
            self._record_user_session_response(trace, response, task_scope=task_scope)
            trace.attempts.append(_fetch_attempt(response, success=True, engine_name=engine_name))
            return response
        except Exception as exc:
            trace.attempts.append(_error_attempt("authenticated_browser", url, exc))
            raise

    def _build_success_result(
        self,
        request: ReadUrlRequest,
        normalized_url: str,
        fetched_at: str,
        trace: ReaderTrace,
        response: FetchResponse,
        extracted: ExtractedText,
    ) -> ReadUrlResult:
        trace.raw_html_hash = sha256_text(response.raw)
        trace.extractor = extracted.extractor
        trace.content_source = "untrusted_web"
        trace.content_hash = sha256_text(extracted.clean_text)
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
        preferred_reason = (
            extracted.extractor if extracted.extractor in {"x_status", "x_article"} else None
        )
        evidence = pick_evidence(
            paragraphs,
            max_items=request.max_evidence_items,
            source_url=response.final_url,
            preferred_text=extracted.primary_text,
            preferred_reason=preferred_reason,
        )
        numbers = extract_numbers(paragraphs, evidence, limit=request.max_number_mentions)
        dates = extract_dates(paragraphs, evidence, limit=request.max_date_mentions)
        entities = extract_entities(paragraphs, evidence, limit=request.max_entity_items)
        financial_events = extract_financial_events(evidence, entities)
        quality_source = response.visible_text or response.text
        quality = score_quality(
            quality_source,
            extracted.clean_text,
            extracted.title,
            len(evidence),
            extractor=extracted.extractor,
        )
        trace.problem_flags = _dedupe_list([*trace.problem_flags, *quality.flags])

        clean_text = _truncate(extracted.clean_text, request.max_clean_text_chars)
        return ReadUrlResult(
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

    def _build_platform_failure_result(
        self,
        request: ReadUrlRequest,
        normalized_url: str,
        fetched_at: str,
        trace: ReaderTrace,
        final_url: str,
        extractor: str,
        code: str,
        flags: list[str],
        message: str,
        suggested_next_action: str,
    ) -> ReadUrlResult:
        problem_flags = _dedupe_list([*trace.problem_flags, *flags])
        trace.extractor = extractor
        trace.content_source = "untrusted_web"
        trace.problem_flags = problem_flags
        return ReadUrlResult(
            success=False,
            url=request.url,
            normalized_url=normalized_url,
            final_url=final_url,
            domain=extract_domain(final_url),
            fetched_at=fetched_at,
            clean_text="",
            summary=None,
            key_points=[],
            quality=ReaderQuality(
                score=0.0,
                level="failed",
                reasons=problem_flags,
                flags=problem_flags,
                metrics={
                    "problem_flags": {flag: True for flag in problem_flags},
                    "text_length": 0,
                    "evidence_count": 0,
                },
            ),
            trace=trace,
            error=ReaderErrorPayload(
                code=code,
                message=message,
                retryable=False,
                suggested_next_action=suggested_next_action,
                type="PlatformExtractionError",
            ),
        )

    def _write_result_cache(
        self,
        normalized_url: str,
        result: ReadUrlResult,
        response: FetchResponse | None,
    ) -> None:
        policy = self._cache_policy(result, response)
        if result.trace:
            result.trace.cache_policy = policy.name
        if policy.should_write and result.trace and result.trace.cache_key:
            self.cache.set(
                result.trace.cache_key,
                normalized_url,
                result.to_dict(),
                ttl_seconds=policy.ttl_seconds,
                cache_policy=policy.name,
            )

    def _save_result_if_requested(
        self,
        request: ReadUrlRequest,
        result: ReadUrlResult,
    ) -> ReadUrlResult:
        result.saved = False
        result.saved_item_id = None
        result.saved_to = None
        result.save_error = None
        if not request.save:
            return result
        if not result.success:
            return result
        try:
            item = reading_item_from_read_result(
                result,
                project=request.project,
                tags=request.tags,
            )
            saved = self._get_storage_manager().save(item, store=request.save_to)
            result.saved = saved.success
            result.saved_item_id = saved.item_id
            result.saved_to = saved.store
            return result
        except Exception as exc:
            if result.trace:
                result.trace.problem_flags = _dedupe_list(
                    [*result.trace.problem_flags, "storage_save_failed"]
                )
            result.saved = False
            result.saved_to = request.save_to
            result.save_error = ReaderErrorPayload(
                code="storage_save_failed",
                message=str(exc),
                retryable=False,
                suggested_next_action="check_store_configuration",
                type=exc.__class__.__name__,
            )
            return result

    def _get_storage_manager(self) -> StorageManager:
        if self._storage_manager is None:
            self._storage_manager = StorageManager.from_env()
        return self._storage_manager

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
                if fetcher is self.browser_session_fetcher:
                    self._record_user_session_response(trace, response, task_scope="read_url")
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
        authenticated_browser = [
            (getattr(self.browser_session_fetcher, "name", "authenticated_browser"), self.browser_session_fetcher)
        ]
        if request.auth_strategy == "user_session_only":
            return authenticated_browser
        if request.fetch_strategy == "http_only":
            plan = http
        elif request.fetch_strategy == "scrapling_first":
            plan = scrapling + browser
        elif request.fetch_strategy == "browser_first":
            plan = browser + http
        elif request.fetch_strategy == "browser_only":
            plan = browser
        else:
            plan = http + scrapling + browser
        if request.auth_strategy == "user_session_fallback":
            return plan + authenticated_browser
        return plan

    def _record_user_session_response(
        self,
        trace: ReaderTrace,
        response: FetchResponse,
        *,
        task_scope: str | None = None,
    ) -> None:
        trace.user_session_used = True
        trace.browser_provider = response.headers.get("x-pyaireader-browser-provider")
        if task_scope and not trace.user_task_scope:
            trace.user_task_scope = task_scope
        trace.visited_urls = _dedupe_list([*trace.visited_urls, response.final_url])

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
                request.auth_strategy,
                request.return_format,
                str(_bucket(request.max_clean_text_chars)),
                str(request.max_evidence_items),
                str(request.max_number_mentions),
                str(request.max_date_mentions),
                str(request.max_entity_items),
                "extractor:v2-platform:v1",
            ]
        )
        return sha256_text(material) or normalized_url

    def _cache_policy(
        self,
        result: ReadUrlResult,
        response: FetchResponse | None,
    ) -> CacheWritePolicy:
        if not result.success:
            return CacheWritePolicy("failure_no_cache", False)
        if response is None:
            return CacheWritePolicy("positive", True, self.config.cache_ttl_seconds)
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


def _dedupe_list(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            output.append(item)
            seen.add(item)
    return output


def _validate_platform_search_request(request: PlatformSearchRequest) -> None:
    if request.platform != "x":
        raise ValueError("platform must be 'x'")
    if not request.query.strip():
        raise ValueError("query must not be empty")
    if request.max_results <= 0:
        raise ValueError("max_results must be greater than 0")
    if request.max_pages <= 0:
        raise ValueError("max_pages must be greater than 0")
    if request.max_results > 100:
        raise ValueError("max_results must be <= 100")
    if request.max_pages > 5:
        raise ValueError("max_pages must be <= 5")


def _platform_search_error(
    request: PlatformSearchRequest,
    trace: ReaderTrace,
    code: str,
    message: str,
    *,
    retryable: bool,
    suggested_next_action: str,
    error_type: str = "PlatformSearchError",
) -> PlatformSearchResult:
    trace.problem_flags = _dedupe_list([*trace.problem_flags, code])
    return PlatformSearchResult(
        success=False,
        platform=request.platform,
        query=request.query,
        items=[],
        trace=trace,
        error=ReaderErrorPayload(
            code=code,
            message=message,
            retryable=retryable,
            suggested_next_action=suggested_next_action,
            type=error_type,
        ),
        visited_urls=trace.visited_urls,
    )


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
        auth_strategy=trace_data.get("auth_strategy"),
        fetch_engine=trace_data.get("fetch_engine"),
        extractor=trace_data.get("extractor"),
        content_source=trace_data.get("content_source", "untrusted_web"),
        content_hash=trace_data.get("content_hash"),
        raw_html_hash=trace_data.get("raw_html_hash"),
        attempts=[FetchAttempt(**item) for item in trace_data.get("attempts", [])],
        redirects=[RedirectHop(**item) for item in trace_data.get("redirects", [])],
        problem_flags=trace_data.get("problem_flags", []),
        user_session_used=trace_data.get("user_session_used", False),
        browser_provider=trace_data.get("browser_provider"),
        visited_urls=trace_data.get("visited_urls", []),
        user_task_scope=trace_data.get("user_task_scope"),
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
        saved=bool(data.get("saved", False)),
        saved_item_id=data.get("saved_item_id"),
        saved_to=data.get("saved_to"),
        save_error=data.get("save_error"),
    )
