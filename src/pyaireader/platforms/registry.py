from __future__ import annotations

from pyaireader.platforms.base import PlatformReader
from pyaireader.platforms.x.article_reader import XArticleReader
from pyaireader.platforms.x.status_reader import XStatusReader


_READERS: tuple[PlatformReader, ...] = (
    XArticleReader(),
    XStatusReader(),
)


def get_platform_reader(url: str) -> PlatformReader | None:
    for reader in _READERS:
        if reader.supports(url):
            return reader
    return None
