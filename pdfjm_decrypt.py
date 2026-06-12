#!/usr/bin/env python3
"""
Decrypt pdfjm.cn encrypted PDF containers after an authorized viewer flow.

You must provide the decode key returned by the site's authorized
`/api/decodeKey` response (`decrypted_data`). This script does not bypass
WeChat authorization, whitelist checks, or any access control.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import getpass
from io import BytesIO
import json
import re
import struct
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import requests


SALT_SIZE = 16
CHUNK_COUNT_SIZE = 4
IV_SIZE = 12
LENGTH_SIZE = 4
KEY_SIZE = 32
PBKDF2_ITERATIONS = 100_000
CDN_PREFIX = "https://cdn.pdfjm.com/"
CDN_URL_RE = re.compile(r"https://cdn\.pdfjm\.com/[^\s\"'<>\\]+?\.pdf(?:\?[^\s\"'<>\\]*)?")
FILE_URL_RE = re.compile(r"\b\d{8}/file/[A-Za-z0-9_./-]+?\.pdf\b")
DECODE_KEY_RE = re.compile(r'"decrypted_data"\s*:\s*"([^"]+)"')
TEXT_URL_RE = re.compile(r"https?://[^\s<>()\"'，。；、]+")


CDN_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Origin": "https://pdfjm.cn",
    "Referer": "https://pdfjm.cn/",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class ContainerError(ValueError):
    """Raised when the encrypted container format is invalid."""


@dataclass
class BrowserCapture:
    decode_key: str | None = None
    file_url: str | None = None
    encrypted_data: bytes | None = None


@dataclass
class NetlogCapture:
    decode_key: str | None = None
    cdn_url: str | None = None
    file_url: str | None = None
    log_capture_mode: str | None = None
    saw_decode_key_request: bool = False
    saw_decode_key_response: bool = False


def derive_key(password: str, salt: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except ModuleNotFoundError as exc:
        raise ContainerError(
            "missing dependency: install with `pip install -r requirements.txt`"
        ) from exc

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def parse_container(data: bytes) -> tuple[bytes, list[bytes], list[bytes]]:
    if len(data) < SALT_SIZE + CHUNK_COUNT_SIZE:
        raise ContainerError("file is too small to be a pdfjm encrypted container")

    offset = 0
    salt = data[offset : offset + SALT_SIZE]
    offset += SALT_SIZE

    chunk_count = struct.unpack_from("<I", data, offset)[0]
    offset += CHUNK_COUNT_SIZE
    if chunk_count == 0:
        raise ContainerError("container declares zero chunks")

    iv_table_size = chunk_count * IV_SIZE
    length_table_size = chunk_count * LENGTH_SIZE
    header_size = SALT_SIZE + CHUNK_COUNT_SIZE + iv_table_size + length_table_size
    if len(data) < header_size:
        raise ContainerError("container header is truncated")

    ivs = [
        data[offset + index * IV_SIZE : offset + (index + 1) * IV_SIZE]
        for index in range(chunk_count)
    ]
    offset += iv_table_size

    lengths = [
        struct.unpack_from("<I", data, offset + index * LENGTH_SIZE)[0]
        for index in range(chunk_count)
    ]
    offset += length_table_size

    ciphertext_size = sum(lengths)
    if ciphertext_size != len(data) - offset:
        raise ContainerError(
            f"ciphertext length mismatch: header says {ciphertext_size} bytes, "
            f"file contains {len(data) - offset} bytes"
        )

    chunks = []
    for length in lengths:
        chunks.append(data[offset : offset + length])
        offset += length

    return salt, ivs, chunks


def decrypt_container(data: bytes, decode_key: str) -> bytes:
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ModuleNotFoundError as exc:
        raise ContainerError(
            "missing dependency: install with `pip install -r requirements.txt`"
        ) from exc

    salt, ivs, chunks = parse_container(data)
    aesgcm = AESGCM(derive_key(decode_key, salt))

    plaintext_parts = []
    for index, (iv, chunk) in enumerate(zip(ivs, chunks), start=1):
        try:
            plaintext_parts.append(aesgcm.decrypt(iv, chunk, None))
        except InvalidTag as exc:
            raise ContainerError(
                f"failed to decrypt chunk {index}; decode key may be incorrect"
            ) from exc

    return b"".join(plaintext_parts)


def download(url: str, timeout: float, headers: dict[str, str] | None = None) -> bytes:
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.content


def download_pdfjm_cdn(url: str, timeout: float) -> bytes:
    return download(url, timeout=timeout, headers=CDN_DOWNLOAD_HEADERS)


def find_key(data: Any, key: str) -> Any:
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_key(item, key)
            if found is not None:
                return found
    return None


def find_pdf_path(data: Any) -> str | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "url" and isinstance(value, str) and value.lower().endswith(".pdf"):
                return value
            found = find_pdf_path(value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_pdf_path(item)
            if found:
                return found
    return None


def cdn_url_from_file_url(file_url: str) -> str:
    if file_url.startswith("http://") or file_url.startswith("https://"):
        return file_url
    return f"{CDN_PREFIX}{file_url.lstrip('/')}"


def iter_json_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_json_strings(item)


def decode_candidate_strings(text: str) -> Iterable[str]:
    yield text

    if "\\u" in text or '\\"' in text:
        try:
            yield bytes(text, "utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            pass

    compact = re.sub(r"\s+", "", text)
    if len(compact) >= 16 and len(compact) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        try:
            yield bytes.fromhex(compact).decode("utf-8", errors="ignore")
        except ValueError:
            pass

    if len(compact) >= 16 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
        padded = compact + "=" * (-len(compact) % 4)
        for candidate in (padded, padded.replace("-", "+").replace("_", "/")):
            try:
                decoded = base64.b64decode(candidate, validate=False)
            except ValueError:
                continue
            yield decoded.decode("utf-8", errors="ignore")


def parse_netlog(path: str) -> NetlogCapture:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))

    capture = NetlogCapture()
    capture.log_capture_mode = (payload.get("constants") or {}).get("logCaptureMode")
    for event in payload.get("events", []):
        params = event.get("params") or {}
        url = params.get("url") or ""
        if "/api/decodeKey" in url:
            capture.saw_decode_key_request = True
        headers = params.get("headers") or []
        if capture.saw_decode_key_request and any(
            isinstance(header, str) and header.startswith("HTTP/1.1 200")
            for header in headers
        ):
            capture.saw_decode_key_response = True

    for raw_text in iter_json_strings(payload):
        for text in decode_candidate_strings(raw_text):
            if not capture.decode_key:
                match = DECODE_KEY_RE.search(text)
                if match:
                    capture.decode_key = match.group(1)

            if not capture.cdn_url:
                match = CDN_URL_RE.search(text)
                if match:
                    capture.cdn_url = match.group(0)

            if not capture.file_url:
                match = FILE_URL_RE.search(text)
                if match:
                    capture.file_url = match.group(0)

            if capture.decode_key and (capture.cdn_url or capture.file_url):
                return capture

    return capture


def load_from_netlog(path: str, timeout: float) -> tuple[bytes, str]:
    capture = parse_netlog(path)
    if not capture.decode_key:
        detail = []
        if capture.log_capture_mode:
            detail.append(f"logCaptureMode={capture.log_capture_mode}")
        if capture.saw_decode_key_request:
            detail.append("/api/decodeKey request was present")
        if capture.saw_decode_key_response:
            detail.append("/api/decodeKey returned 200")
        suffix = f" ({'; '.join(detail)})" if detail else ""
        raise ContainerError(
            "netlog did not contain decrypted_data response body"
            f"{suffix}. Re-export with "
            "`Include raw bytes` enabled, or use -u/--encrypted-file with --decode-key."
        )

    file_url = capture.cdn_url or (cdn_url_from_file_url(capture.file_url) if capture.file_url else None)
    if not file_url:
        raise ContainerError("netlog did not contain a pdfjm CDN PDF URL")

    print(f"captured CDN URL from netlog: {file_url}")
    encrypted = download_pdfjm_cdn(file_url, timeout=timeout)
    return encrypted, capture.decode_key


def capture_authorized_browser_flow(
    share_url: str,
    timeout: float,
    headless: bool,
    wait_for_close: bool,
) -> tuple[bytes, str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise ContainerError(
            "missing dependency: install with `pip install -r requirements.txt` "
            "and `python -m playwright install chromium`"
        ) from exc

    capture = BrowserCapture()

    def handle_response(response: Any) -> None:
        url = response.url
        try:
            if "/api/decodeKey" in url:
                payload = response.json()
                decode_key = find_key(payload, "decrypted_data")
                if isinstance(decode_key, str) and decode_key:
                    capture.decode_key = decode_key
                    print("captured decode key")

            if "/go-api/fileInfo" in url:
                payload = response.json()
                file_url = find_pdf_path(payload)
                if file_url:
                    capture.file_url = file_url
                    print(f"captured file url: {file_url}")

            if "cdn.pdfjm.com/" in url and url.lower().split("?")[0].endswith(".pdf"):
                body = response.body()
                if body:
                    capture.encrypted_data = body
                    print(f"captured CDN file: {len(body)} bytes")
        except PlaywrightError:
            return
        except ValueError:
            return

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        page.on("response", handle_response)

        print("opening browser; scan the QR code in the opened page")
        page.goto(share_url, wait_until="domcontentloaded")

        deadline = time.monotonic() + timeout
        captured_notice_shown = False
        while time.monotonic() < deadline:
            captured = capture.decode_key and (capture.encrypted_data or capture.file_url)
            if captured and not wait_for_close:
                break
            if captured and wait_for_close and not captured_notice_shown:
                print("authorized data captured; close the browser window to continue")
                captured_notice_shown = True
            if page.is_closed():
                break
            page.wait_for_timeout(500)

        try:
            browser.close()
        except PlaywrightError:
            pass

    if not capture.decode_key:
        raise ContainerError(
            "did not capture /api/decodeKey decrypted_data; scan may not have completed"
        )

    encrypted = capture.encrypted_data
    if encrypted is None:
        if not capture.file_url:
            raise ContainerError("did not capture CDN file or fileInfo PDF URL")
        encrypted = download_pdfjm_cdn(cdn_url_from_file_url(capture.file_url), timeout=60.0)

    return encrypted, capture.decode_key


def read_decode_key(args: argparse.Namespace) -> str:
    if args.decode_key:
        return args.decode_key

    if args.decode_key_file:
        return Path(args.decode_key_file).read_text(encoding="utf-8").strip()

    return getpass.getpass("decode key (decrypted_data): ").strip()


def extract_pdf_text(pdf_data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise ContainerError(
            "missing dependency: install with `pip install -r requirements.txt`"
        ) from exc

    reader = PdfReader(BytesIO(pdf_data))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n\n--- page {index} ---\n{text}".strip())
    return "\n".join(pages).strip()


def clean_link_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.replace("\u200b", "")).strip(" 丨|")


def clean_tsv_field(value: str) -> str:
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def extract_pdf_links(pdf_data: bytes) -> list[tuple[int, str, str, str]]:
    try:
        return extract_pdf_links_with_labels(pdf_data)
    except ModuleNotFoundError:
        return extract_pdf_links_with_pypdf(pdf_data)


def extract_pdf_links_with_labels(pdf_data: bytes) -> list[tuple[int, str, str, str]]:
    try:
        import fitz
    except ModuleNotFoundError as exc:
        raise exc

    doc = fitz.open(stream=pdf_data, filetype="pdf")
    links: list[tuple[int, str, str, str]] = []
    seen: set[tuple[int, str, str, str]] = set()

    def add(page_number: int, source: str, label: str, url: str) -> None:
        cleaned_url = url.strip().rstrip(".,;:!?)]}，。；：！？）】》")
        cleaned_label = clean_link_label(label)
        if not cleaned_url:
            return
        item = (page_number, source, cleaned_label, cleaned_url)
        if item not in seen:
            seen.add(item)
            links.append(item)

    for page_number, page in enumerate(doc, start=1):
        for link in page.get_links():
            uri = link.get("uri")
            rect = link.get("from")
            if not uri or rect is None:
                continue
            label = page.get_textbox(fitz.Rect(rect))
            add(page_number, "annotation", label, uri)

        text = page.get_text("text") or ""
        for match in TEXT_URL_RE.finditer(text):
            url = match.group(0)
            add(page_number, "text", url, url)

    return links


def extract_pdf_links_with_pypdf(pdf_data: bytes) -> list[tuple[int, str, str, str]]:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise ContainerError(
            "missing dependency: install with `pip install -r requirements.txt`"
        ) from exc

    reader = PdfReader(BytesIO(pdf_data))
    links: list[tuple[int, str, str, str]] = []
    seen: set[tuple[int, str, str, str]] = set()

    def add(page_number: int, source: str, label: str, url: str) -> None:
        cleaned = url.strip().rstrip(".,;:!?)]}，。；：！？）】》")
        if not cleaned:
            return
        item = (page_number, source, clean_link_label(label), cleaned)
        if item not in seen:
            seen.add(item)
            links.append(item)

    for page_number, page in enumerate(reader.pages, start=1):
        annotations = page.get("/Annots") or []
        for annotation_ref in annotations:
            annotation = annotation_ref.get_object()
            action = annotation.get("/A") or {}
            uri = action.get("/URI")
            if uri:
                add(page_number, "annotation", "", str(uri))

        text = page.extract_text() or ""
        for match in TEXT_URL_RE.finditer(text):
            add(page_number, "text", match.group(0), match.group(0))

    return links


def write_text_output(pdf_data: bytes, output_path: Path, text_output: str | None) -> None:
    text_path = Path(text_output) if text_output else output_path.with_suffix(".txt")
    text = extract_pdf_text(pdf_data)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")
    print(f"wrote extracted text to {text_path}")


def write_links_output(pdf_data: bytes, output_path: Path, links_output: str | None) -> None:
    links_path = Path(links_output) if links_output else output_path.with_suffix(".links.txt")
    links = extract_pdf_links(pdf_data)
    header = "page\tsource\tlabel\turl"
    lines = [
        f"{page_number}\t{source}\t{clean_tsv_field(label)}\t{clean_tsv_field(url)}"
        for page_number, source, label, url in links
    ]
    links_path.parent.mkdir(parents=True, exist_ok=True)
    links_path.write_text("\n".join([header, *lines]), encoding="utf-8")
    print(f"wrote {len(links)} links to {links_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decrypt a pdfjm.cn encrypted PDF container after an authorized flow."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "-i",
        "--encrypted-file",
        help="Path to the downloaded encrypted .pdf container.",
    )
    source.add_argument(
        "-u",
        "--url",
        help="Direct CDN URL for the encrypted .pdf container.",
    )
    source.add_argument(
        "--share-url",
        help="Share page URL. Opens a browser, waits for manual scan, then captures authorized data.",
    )
    source.add_argument(
        "--netlog",
        help="Chrome net-export JSON captured after a normal authorized browser flow.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path for the decrypted plaintext PDF.",
    )
    parser.add_argument(
        "--decode-key",
        help="Authorized /api/decodeKey decrypted_data value. Omit to enter securely.",
    )
    parser.add_argument(
        "--decode-key-file",
        help="UTF-8 text file containing the authorized decrypted_data value.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds when using --url. Default: 60.",
    )
    parser.add_argument(
        "--browser-timeout",
        type=float,
        default=300.0,
        help="Seconds to wait for QR scan and viewer network requests. Default: 300.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser without a visible window. Not useful for QR scanning.",
    )
    parser.add_argument(
        "--wait-for-close",
        action="store_true",
        help="After capture, wait until you manually close the browser window.",
    )
    parser.add_argument(
        "--text-output",
        help="Path for extracted PDF text. Default: output path with .txt suffix.",
    )
    parser.add_argument(
        "--no-text",
        action="store_true",
        help="Skip extracting text from the decrypted PDF.",
    )
    parser.add_argument(
        "--links-output",
        help="Path for extracted PDF links. Default: output path with .links.txt suffix.",
    )
    parser.add_argument(
        "--no-links",
        action="store_true",
        help="Skip extracting links from the decrypted PDF.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.decode_key and args.decode_key_file:
        parser.error("use only one of --decode-key or --decode-key-file")
    if (args.share_url or args.netlog) and (args.decode_key or args.decode_key_file):
        parser.error("--share-url/--netlog capture the decode key from authorized data")

    try:
        if args.share_url:
            encrypted, decode_key = capture_authorized_browser_flow(
                args.share_url,
                args.browser_timeout,
                args.headless,
                args.wait_for_close,
            )
        elif args.netlog:
            encrypted, decode_key = load_from_netlog(args.netlog, args.timeout)
        else:
            decode_key = read_decode_key(args)
            if not decode_key:
                raise ContainerError("decode key is empty")

            if args.url:
                encrypted = (
                    download_pdfjm_cdn(args.url, args.timeout)
                    if "cdn.pdfjm.com/" in args.url
                    else download(args.url, args.timeout)
                )
            else:
                encrypted = Path(args.encrypted_file).read_bytes()

        plaintext = decrypt_container(encrypted, decode_key)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(plaintext)

        if not plaintext.startswith(b"%PDF"):
            print(
                "warning: decrypted output does not start with %PDF; "
                "verify the decode key and container source",
                file=sys.stderr,
            )

        print(f"wrote {len(plaintext)} bytes to {output_path}")
        if not args.no_text:
            write_text_output(plaintext, output_path, args.text_output)
        if not args.no_links:
            write_links_output(plaintext, output_path, args.links_output)
        return 0
    except (OSError, requests.RequestException, ContainerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
