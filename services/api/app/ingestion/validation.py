"""
Validation of uploaded files, done before anything is stored.

An upload is checked by name, size, and CONTENT. The extension alone proves nothing, so
each format's leading bytes (and, for Office files, the archive structure) must match.
Filenames are sanitised before they are used in a storage key.
"""

import hashlib
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, Dict, Optional

from app.ingestion.errors import FileTooLarge, InvalidUpload, UnsupportedFormat

# Office files are ZIP archives; refuse ones that would expand absurdly (a "zip bomb").
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5000

LEGACY_FORMATS = {
    "doc": "Legacy .doc files cannot be read. Save the document as .docx and upload that.",
    "ppt": "Legacy .ppt files cannot be read. Save the presentation as .pptx and upload that.",
    "xls": "Spreadsheets are not supported.",
}


@dataclass(frozen=True)
class FileKind:
    extension: str
    kind: str            # document | text | video | audio
    content_type: str    # the platform's ContentItem.content_type
    mime: str


FILE_KINDS: Dict[str, FileKind] = {
    "pdf": FileKind("pdf", "document", "DOCUMENT", "application/pdf"),
    "docx": FileKind("docx", "document", "DOCUMENT", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "pptx": FileKind("pptx", "document", "DOCUMENT", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "txt": FileKind("txt", "text", "ARTICLE", "text/plain"),
    "md": FileKind("md", "text", "ARTICLE", "text/markdown"),
    "markdown": FileKind("markdown", "text", "ARTICLE", "text/markdown"),
    "mp4": FileKind("mp4", "video", "VIDEO", "video/mp4"),
    "mov": FileKind("mov", "video", "VIDEO", "video/quicktime"),
    "webm": FileKind("webm", "video", "VIDEO", "video/webm"),
    "mp3": FileKind("mp3", "audio", "AUDIO", "audio/mpeg"),
    "wav": FileKind("wav", "audio", "AUDIO", "audio/wav"),
    "m4a": FileKind("m4a", "audio", "AUDIO", "audio/mp4"),
}


@dataclass(frozen=True)
class ValidatedUpload:
    extension: str
    kind: FileKind
    safe_name: str
    size: int
    sha256: str


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """A safe file name: basename only, restricted characters, never empty, extension kept."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().strip(".")
    stem, dot, extension = base.rpartition(".")
    if not dot:
        stem, extension = base, ""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "file"
    extension = re.sub(r"[^A-Za-z0-9]", "", extension).lower()[:10]
    stem = stem[: max(1, max_length - len(extension) - 1)]
    return f"{stem}.{extension}" if extension else stem


def _is_zip_of(data: bytes, required_prefix: str) -> bool:
    """A real Office archive: a valid zip with [Content_Types].xml and the expected part folder."""
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES or sum(e.file_size for e in entries) > MAX_UNCOMPRESSED_BYTES:
                return False
            names = {e.filename for e in entries}
            return "[Content_Types].xml" in names and any(n.startswith(required_prefix) for n in names)
    except zipfile.BadZipFile:
        return False


def _is_utf8_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return True


def _is_mp3(data: bytes) -> bool:
    return data.startswith(b"ID3") or (len(data) > 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)


SIGNATURE_CHECKS: Dict[str, Callable[[bytes], bool]] = {
    "pdf": lambda d: d.lstrip(b"\x00\t\n\r ")[:5] == b"%PDF-",
    "docx": lambda d: _is_zip_of(d, "word/"),
    "pptx": lambda d: _is_zip_of(d, "ppt/"),
    "txt": _is_utf8_text,
    "md": _is_utf8_text,
    "markdown": _is_utf8_text,
    "mp4": lambda d: d[4:8] == b"ftyp",
    "mov": lambda d: d[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free"),
    "m4a": lambda d: d[4:8] == b"ftyp",
    "webm": lambda d: d[:4] == b"\x1a\x45\xdf\xa3",
    "mp3": _is_mp3,
    "wav": lambda d: d[:4] == b"RIFF" and d[8:12] == b"WAVE",
}


def allowed_extensions(configured: Optional[str] = None) -> list[str]:
    """Supported extensions, optionally narrowed by the ALLOWED_FILE_TYPES setting."""
    if not configured:
        return sorted(FILE_KINDS)
    wanted = {e.strip().lower().lstrip(".") for e in configured.split(",") if e.strip()}
    return sorted(e for e in FILE_KINDS if e in wanted)


def validate_upload(
    filename: str, data: bytes, *, max_bytes: int, allowed: Optional[list[str]] = None
) -> ValidatedUpload:
    """Raise a specific IngestionError, or return what the pipeline needs to know."""
    if not data:
        raise InvalidUpload("The file is empty.")
    if len(data) > max_bytes:
        raise FileTooLarge(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.")

    safe_name = sanitize_filename(filename)
    extension = safe_name.rpartition(".")[2].lower() if "." in safe_name else ""

    if extension in LEGACY_FORMATS:
        raise UnsupportedFormat(LEGACY_FORMATS[extension], code="legacy_format")
    supported = allowed if allowed is not None else sorted(FILE_KINDS)
    if extension not in FILE_KINDS or extension not in supported:
        shown = ", ".join(f".{e}" for e in supported)
        raise UnsupportedFormat(f"'.{extension or '?'}' files are not supported. Supported types: {shown}.")

    if not SIGNATURE_CHECKS[extension](data):
        raise InvalidUpload(
            f"The file's contents do not look like a real .{extension} file. "
            "It may be corrupt or have the wrong extension.",
            code="content_mismatch",
        )

    return ValidatedUpload(
        extension=extension,
        kind=FILE_KINDS[extension],
        safe_name=safe_name,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def storage_key(org_id, job_id, safe_name: str) -> str:
    """Object key for an upload. Every part is a UUID or a sanitised name: nothing user-controlled reaches the path."""
    return f"{org_id}/{job_id}/{safe_name}"
