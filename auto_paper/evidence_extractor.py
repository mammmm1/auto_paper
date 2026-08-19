from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader


EVIDENCE_SCHEMA_VERSION = "2026-08-19-v2"
MAX_PDF_MB = 60
MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024
MAX_PAGES = 100
USER_AGENT = "auto_paper/0.2 (+https://github.com/mammmm1/auto_paper)"
CODE_HOSTS = {"github.com", "gitlab.com", "huggingface.co", "bitbucket.org"}
CODE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co|bitbucket\.org)/"
    r"[^\s<>{}\[\]\"']+",
    re.IGNORECASE,
)
SECTION_TERMS = {
    "method": (
        "proposed method",
        "methodology",
        "our method",
        "architecture",
        "network architecture",
        "framework",
    ),
    "experiment": (
        "experiments",
        "experimental results",
        "implementation details",
        "evaluation",
        "quantitative results",
    ),
    "ablation": (
        "ablation study",
        "ablation studies",
        "component analysis",
        "effectiveness of",
    ),
    "dataset": (
        "datasets",
        "dataset and metrics",
        "experimental setup",
        "benchmark dataset",
    ),
    "conclusion": (
        "conclusion",
        "conclusions",
        "discussion",
        "limitations",
    ),
}
SECTION_LABELS = {
    "method": "方法/架构",
    "experiment": "实验结果",
    "ablation": "消融证据",
    "dataset": "数据与设置",
    "conclusion": "结论与限制",
}
SECTION_HEADINGS = {
    "method": {
        "method",
        "methods",
        "ourmethod",
        "proposedmethod",
        "methodology",
        "proposedapproach",
        "networkarchitecture",
        "overallarchitecture",
    },
    "experiment": {
        "experiment",
        "experiments",
        "experimentalresults",
        "results",
        "evaluation",
    },
    "ablation": {
        "ablation",
        "ablations",
        "ablationstudy",
        "ablationstudies",
        "analysisandablation",
    },
    "dataset": {
        "dataset",
        "datasets",
        "experimentaldataset",
        "experimentalsetup",
        "datasetsandexactsplits",
    },
    "conclusion": {
        "conclusion",
        "conclusions",
        "discussion",
        "limitations",
        "limitationsanddiscussion",
    },
}


def evidence_input_hash(paper: dict[str, Any]) -> str:
    payload = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "pdf_url": paper.get("pdf_url") or "",
        "external_id": paper.get("external_id") or "",
        "updated_at": paper.get("updated_at") or "",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def collect_paper_evidence(
    paper: dict[str, Any],
    cache_dir: Path,
    force: bool = False,
) -> dict[str, Any]:
    pdf_url = str(paper.get("pdf_url") or "").strip()
    _validate_pdf_url(pdf_url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(pdf_url.encode("utf-8")).hexdigest()[:24]
    pdf_path = cache_dir / f"{cache_key}.pdf"
    if force or not _is_cached_pdf(pdf_path):
        _download_pdf(pdf_url, pdf_path)

    pages, annotation_urls = _extract_pdf(pdf_path)
    text_chars = sum(len(page) for page in pages)
    snippets = extract_evidence_from_pages(pages)
    code_urls = extract_code_urls("\n".join(pages), annotation_urls)
    code_evidence = verify_code_urls(code_urls[:5])
    limitations: list[str] = []
    status = "verified"
    if text_chars < 800:
        status = "text_insufficient"
        limitations.append("PDF 可读取，但正文文本不足；可能是扫描版、字体编码异常或内容过短，需要 OCR。")
    if not snippets:
        limitations.append("未能稳定定位方法或实验段落，需要人工打开 PDF 复核。")
    if not code_evidence["urls"]:
        limitations.append("正文与 PDF 链接注释中未发现受支持的代码仓库地址。")

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": status,
        "pdf": {
            "url": pdf_url,
            "cache_file": pdf_path.name,
            "sha256": _file_sha256(pdf_path),
            "size_bytes": pdf_path.stat().st_size,
            "page_count": len(pages),
            "text_chars": text_chars,
        },
        "sections": snippets,
        "code": code_evidence,
        "limitations": limitations,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def extract_evidence_from_pages(pages: list[str]) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for kind, terms in SECTION_TERMS.items():
        best: tuple[float, int, int, str] | None = None
        for page_index, page_text in enumerate(pages):
            normalized = _normalize_text(page_text)
            lowered = normalized.lower()
            heading = _section_heading(page_text, kind)
            if heading:
                heading_position = normalized.find(heading)
                if heading_position < 0:
                    heading_position = lowered.find(heading.lower())
                candidate = (40.0, page_index, max(0, heading_position), heading)
                if best is None or candidate[0] > best[0]:
                    best = candidate
            for term_index, term in enumerate(terms):
                if term not in lowered:
                    continue
                position = lowered.find(term)
                specificity = (len(terms) - term_index) * 2.5
                frequency = min(lowered.count(term), 3)
                heading_case = 5 if term.title() in normalized else 0
                if kind == "method":
                    page_bias = max(0, 6 - page_index) * 0.25
                elif kind in {"experiment", "ablation", "conclusion"}:
                    page_bias = min(page_index, 8) * 0.18
                else:
                    page_bias = 0
                candidate = (
                    specificity + frequency + heading_case + page_bias,
                    page_index,
                    position,
                    term,
                )
                if best is None or candidate[0] > best[0]:
                    best = candidate
        if best is None:
            continue
        _, page_index, position, matched_term = best
        text = _normalize_text(pages[page_index])
        snippets.append(
            {
                "kind": kind,
                "label": SECTION_LABELS[kind],
                "page": page_index + 1,
                "matched_term": matched_term,
                "text": _snippet_window(text, position, 900),
            }
        )
    return snippets


def extract_code_urls(text: str, annotation_urls: list[str] | None = None) -> list[str]:
    candidates = [match.group(0) for match in CODE_URL_PATTERN.finditer(text)]
    candidates.extend(annotation_urls or [])
    normalized: list[str] = []
    for candidate in candidates:
        url = _normalize_code_url(candidate)
        if url and url not in normalized:
            normalized.append(url)
    return normalized


def verify_code_urls(urls: list[str]) -> dict[str, Any]:
    results = []
    for url in urls:
        verified, status_code = _verify_url(url)
        results.append({"url": url, "verified": verified, "http_status": status_code})
    if any(item["verified"] for item in results):
        status = "verified_repository"
    elif results:
        status = "reported_repository"
    else:
        status = "not_found"
    return {"status": status, "urls": results}


def _validate_pdf_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("论文缺少可用的 HTTP(S) PDF 地址")


def _download_pdf(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            _stream_response(request, destination)
            return
        except urllib.error.URLError as exc:
            last_error = exc
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                try:
                    context = ssl._create_unverified_context()
                    _stream_response(request, destination, context=context)
                    return
                except (OSError, urllib.error.URLError, TimeoutError) as fallback_exc:
                    last_error = fallback_exc
        except (OSError, TimeoutError) as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(1.2 * (attempt + 1))
    raise OSError(f"PDF 下载失败：{last_error}")


def _stream_response(
    request: urllib.request.Request,
    destination: Path,
    context: ssl.SSLContext | None = None,
) -> None:
    temp_path = destination.with_suffix(".part")
    try:
        with urllib.request.urlopen(request, timeout=45, context=context) as response:
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > MAX_PDF_BYTES:
                raise ValueError(f"PDF 超过 {MAX_PDF_MB} MB 限制")
            total = 0
            prefix = b""
            with temp_path.open("wb") as target:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    if len(prefix) < 1024:
                        prefix = (prefix + chunk)[:1024]
                    total += len(chunk)
                    if total > MAX_PDF_BYTES:
                        raise ValueError(f"PDF 超过 {MAX_PDF_MB} MB 限制")
                    target.write(chunk)
            if b"%PDF-" not in prefix:
                raise ValueError("下载内容不是有效 PDF")
        temp_path.replace(destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _extract_pdf(path: Path) -> tuple[list[str], list[str]]:
    reader = PdfReader(path, strict=False)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 - encrypted PDFs need an actionable status.
            raise ValueError("PDF 已加密，无法提取正文") from exc
    pages: list[str] = []
    annotation_urls: list[str] = []
    for page in reader.pages[:MAX_PAGES]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - keep other pages usable when one page is malformed.
            pages.append("")
        annotation_urls.extend(_annotation_urls(page))
    return pages, annotation_urls


def _annotation_urls(page: Any) -> list[str]:
    urls: list[str] = []
    try:
        annotations = page.get("/Annots") or []
        for annotation_ref in annotations:
            annotation = annotation_ref.get_object()
            action = annotation.get("/A") or {}
            uri = str(action.get("/URI") or "")
            if uri:
                urls.append(uri)
    except Exception:  # noqa: BLE001 - annotations are optional evidence.
        return urls
    return urls


def _normalize_code_url(candidate: str) -> str:
    value = str(candidate).strip().rstrip(".,;:!?)]}>'\"")
    parsed = urllib.parse.urlparse(value)
    host = parsed.netloc.lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or host not in CODE_HOSTS:
        return ""
    path_parts = [part for part in parsed.path.split("/") if part]
    if host in {"github.com", "gitlab.com", "bitbucket.org"} and len(path_parts) < 2:
        return ""
    clean_path = "/" + "/".join(path_parts)
    return urllib.parse.urlunparse(("https", host, clean_path, "", "", ""))


def _verify_url(url: str) -> tuple[bool, int | None]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Range": "bytes=0-1024"},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            response.read(512)
            status = int(response.status)
            return 200 <= status < 400, status
    except urllib.error.HTTPError as exc:
        return False, int(exc.code)
    except (OSError, urllib.error.URLError, TimeoutError):
        return False, None


def _is_cached_pdf(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 1024:
        return False
    with path.open("rb") as source:
        return b"%PDF-" in source.read(1024)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_text(text: str) -> str:
    return " ".join(str(text).replace("\x00", " ").split())


def _section_heading(page_text: str, kind: str) -> str:
    headings = SECTION_HEADINGS[kind]
    for raw_line in str(page_text).splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line or len(line) > 90:
            continue
        without_number = re.sub(
            r"^(?:(?:[IVXLCDM]+|\d+)[.)]?)\s+",
            "",
            line,
            flags=re.IGNORECASE,
        )
        canonical = re.sub(r"[^a-z]", "", without_number.lower())
        if canonical in headings:
            return without_number
    return ""


def _snippet_window(text: str, position: int, limit: int) -> str:
    start = max(0, position - 120)
    end = min(len(text), start + limit)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(text):
        snippet = f"{snippet}…"
    return snippet
