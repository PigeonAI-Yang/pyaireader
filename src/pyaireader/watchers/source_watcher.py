from __future__ import annotations

import xml.etree.ElementTree as ET


def extract_urls_from_rss(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    urls: list[str] = []
    for item in root.findall(".//item"):
        link = item.findtext("link")
        if link and link.strip():
            urls.append(link.strip())
    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        for link in entry.findall("{http://www.w3.org/2005/Atom}link"):
            href = link.attrib.get("href")
            if href:
                urls.append(href.strip())
    return _dedupe(urls)


def extract_urls_from_sitemap(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    urls: list[str] = []
    for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
        if loc.text and loc.text.strip():
            urls.append(loc.text.strip())
    for loc in root.findall(".//loc"):
        if loc.text and loc.text.strip():
            urls.append(loc.text.strip())
    return _dedupe(urls)


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        output.append(url)
    return output
