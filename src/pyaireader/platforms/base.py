from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from pyaireader.extractors import ExtractedText
from pyaireader.fetchers import FetchResponse
from pyaireader.models import ReadUrlRequest, ReadUrlResult, ReaderTrace


FetchUrl = Callable[[str], FetchResponse]
FetchUserSessionUrl = Callable[[str, str | None], FetchResponse]
SuccessBuilder = Callable[[FetchResponse, ExtractedText], ReadUrlResult]
FailureBuilder = Callable[
    [str, str, str, list[str], str, str],
    ReadUrlResult,
]


@dataclass(frozen=True)
class PlatformContext:
    request: ReadUrlRequest
    normalized_url: str
    fetched_at: str
    trace: ReaderTrace
    fetch_url: FetchUrl
    fetch_user_session_url: FetchUserSessionUrl | None
    build_success_result: SuccessBuilder
    build_failure_result: FailureBuilder


class PlatformReader(Protocol):
    name: str

    def supports(self, url: str) -> bool:
        ...

    def read(self, context: PlatformContext) -> ReadUrlResult | None:
        ...
