"""Download files from Google Drive share links."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import httpx

DRIVE_ID_PATTERNS = [
    re.compile(r"drive\.google\.com/open\?id=([^&]+)", re.I),
    re.compile(r"drive\.google\.com/file/d/([^/]+)", re.I),
    re.compile(r"drive\.google\.com/uc\?(?:export=download&)?id=([^&]+)", re.I),
    re.compile(r"docs\.google\.com/uc\?.*?id=([^&]+)", re.I),
]


def extract_google_drive_file_id(url: str) -> str | None:
    url = (url or "").strip()
    if not url:
        return None
    for pattern in DRIVE_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def _safe_filename(name: str, file_id: str) -> str:
    base = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
    if not base:
        base = "resume"
    return f"{base}_{file_id[:8]}.pdf"


def _filename_from_content_disposition(header: str) -> str | None:
    if not header:
        return None
    match = re.search(r"filename\*=UTF-8''([^;\s]+)", header, re.I)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1))
    match = re.search(r'filename="([^"]+)"', header)
    if match:
        return match.group(1)
    match = re.search(r"filename=([^;\s]+)", header, re.I)
    return match.group(1) if match else None


def _sanitize_drive_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "", (name or "").strip())
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned or "resume.pdf"


async def download_google_drive_pdf(
    url: str,
    dest_dir: Path,
    client: httpx.AsyncClient,
    preferred_name: str = "",
) -> Path:
    """Download a PDF from a public Google Drive link."""
    file_id = extract_google_drive_file_id(url)
    if not file_id:
        raise ValueError(f"Could not parse Google Drive file id from URL: {url}")

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    base_url = "https://drive.google.com/uc?export=download&id=" + file_id
    response = await client.get(base_url, follow_redirects=True)

    # Large files return an HTML virus-scan confirmation page.
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" in content_type and file_id in response.text:
        confirm_match = re.search(r"confirm=([0-9A-Za-z_]+)", response.text)
        token_match = re.search(r"name=\"confirm\"\s+value=\"([^\"]+)\"", response.text)
        confirm = None
        if confirm_match:
            confirm = confirm_match.group(1)
        elif token_match:
            confirm = token_match.group(1)
        if confirm:
            confirm_url = f"{base_url}&confirm={confirm}"
            response = await client.get(confirm_url, follow_redirects=True)
            content_type = response.headers.get("content-type", "").lower()

    if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
        raise ValueError(
            f"Downloaded file is not a PDF (content-type={content_type}). "
            "Ensure the Drive link is shared as 'Anyone with the link'."
        )

    original_name = _filename_from_content_disposition(
        response.headers.get("content-disposition", "")
    )
    if original_name and original_name.lower().endswith(".pdf"):
        dest = dest_dir / _sanitize_drive_filename(original_name)
    else:
        dest = dest_dir / _safe_filename(preferred_name, file_id)

    dest.write_bytes(response.content)
    return dest


async def download_google_drive_pdfs(
    items: list[tuple[str, str]],
    dest_dir: Path,
    timeout: float = 60.0,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[tuple[str, Path]]:
    """
    Download multiple Drive PDFs.
    items: list of (url, preferred_name)
    Returns list of (url, local_path) for successes.
    """
    dest_dir = Path(dest_dir)
    results: list[tuple[str, Path]] = []
    errors: list[str] = []

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": "ResumeVerify/1.0"},
        follow_redirects=True,
    ) as client:
        total = len(items)
        for index, (url, name) in enumerate(items):
            try:
                path = await download_google_drive_pdf(url, dest_dir, client, name)
                results.append((url, path))
            except Exception as exc:
                errors.append(f"{name or url}: {exc}")
            if progress_callback:
                progress_callback(index + 1, total)

    if errors and not results:
        raise ValueError("No resumes downloaded. " + "; ".join(errors[:3]))
    return results
