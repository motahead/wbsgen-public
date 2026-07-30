"""Load JSON and generated HTML source documents by their contents."""

from __future__ import annotations

import copy
import json
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path

from .version import VERSION


class SourceFormat(str, Enum):
    JSON = "json"
    HTML = "html"


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    format: SourceFormat
    data: dict[str, object]


class _EmbeddedSourceCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.source_texts: list[str] = []
        self._chunks: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag != "script":
            return
        attributes = dict(attrs)
        if (
            attributes.get("id") == "wbsgen-source"
            and attributes.get("type") == "application/json"
        ):
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._chunks is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._chunks is not None:
            self.source_texts.append("".join(self._chunks))
            self._chunks = None


def extract_html_source(html_text: str) -> dict[str, object]:
    """Extract the single embedded source JSON object from generated HTML."""

    collector = _EmbeddedSourceCollector()
    collector.feed(html_text)
    collector.close()
    if not collector.source_texts:
        raise ValueError("embedded source JSON not found")
    if len(collector.source_texts) != 1:
        raise ValueError("embedded source JSON must appear exactly once")
    try:
        data = json.loads(collector.source_texts[0])
    except json.JSONDecodeError as exc:
        raise ValueError("invalid embedded source JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("embedded source JSON root must be an object")
    return data


def load_source(
    path: Path, *, allowed: frozenset[SourceFormat] | None = None
) -> SourceDocument:
    """Read a JSON object or generated HTML source document from *path*."""

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"source file is not valid UTF-8: {path}") from exc

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        data = extract_html_source(text)
        source_format = SourceFormat.HTML
    else:
        if isinstance(parsed, dict):
            data = parsed
            source_format = SourceFormat.JSON
        else:
            data = extract_html_source(text)
            source_format = SourceFormat.HTML

    if allowed is not None and source_format not in allowed:
        allowed_formats = ", ".join(
            source_format.value
            for source_format in SourceFormat
            if source_format in allowed
        )
        raise ValueError(
            f"input source format is {source_format.value}; "
            f"allowed formats: {allowed_formats or 'none'}"
        )
    return SourceDocument(path=path, format=source_format, data=data)


def format_source_json(data: dict[str, object]) -> str:
    """Return a consistently formatted JSON representation of source data."""

    return json.dumps(data, ensure_ascii=False, indent=2)


def read_generator_version(data: dict[str, object]) -> str | None:
    """Return the optional generator version stored in source metadata."""

    if "_wbsgen" not in data:
        return None
    metadata = data["_wbsgen"]
    if not isinstance(metadata, dict):
        raise ValueError("_wbsgen metadata must be an object")
    if "generatorVersion" not in metadata:
        return None
    version = metadata["generatorVersion"]
    if not isinstance(version, str):
        raise ValueError("_wbsgen.generatorVersion must be a string")
    return version


def with_generator_version(
    data: dict[str, object], version: str = VERSION
) -> dict[str, object]:
    """Return a deep-copied source document annotated with generator metadata."""

    read_generator_version(data)
    result = copy.deepcopy(data)
    if "_wbsgen" not in result:
        metadata = {}
        result["_wbsgen"] = metadata
    else:
        metadata = result["_wbsgen"]
    if not isinstance(metadata, dict):
        raise ValueError("_wbsgen metadata must be an object")
    metadata["generatorVersion"] = version
    return result


def read_generated_at(data: dict[str, object]) -> str | None:
    """Return the optional last-generated timestamp stored in source metadata."""

    if "_wbsgen" not in data:
        return None
    metadata = data["_wbsgen"]
    if not isinstance(metadata, dict):
        raise ValueError("_wbsgen metadata must be an object")
    if "generatedAt" not in metadata:
        return None
    generated_at = metadata["generatedAt"]
    if not isinstance(generated_at, str):
        raise ValueError("_wbsgen.generatedAt must be a string")
    return generated_at


def with_generated_at(
    data: dict[str, object], generated_at: str | None = None
) -> dict[str, object]:
    """Return a deep-copied source document annotated with the last-generated timestamp."""

    read_generated_at(data)
    if generated_at is None:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    result = copy.deepcopy(data)
    if "_wbsgen" not in result:
        metadata = {}
        result["_wbsgen"] = metadata
    else:
        metadata = result["_wbsgen"]
    if not isinstance(metadata, dict):
        raise ValueError("_wbsgen metadata must be an object")
    metadata["generatedAt"] = generated_at
    return result


def paths_refer_to_same_file(input_path: Path, output_path: Path) -> bool:
    """Return whether two paths resolve to the same filesystem object."""

    try:
        return input_path.samefile(output_path)
    except FileNotFoundError:
        return input_path.resolve() == output_path.resolve()
    except OSError as exc:
        raise ValueError(
            f"failed to compare HTML output with input JSON: {output_path}"
        ) from exc


def ensure_output_available(
    input_path: Path | None, output_path: Path, *, overwrite: bool
) -> None:
    """Reject output paths that would overwrite a protected source or file."""

    if input_path is not None and paths_refer_to_same_file(input_path, output_path):
        raise ValueError(f"output file must differ from input file: {output_path}")
    if (output_path.exists() or output_path.is_symlink()) and not overwrite:
        raise ValueError(f"output file already exists: {output_path}")


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically replace *path* without following an existing symlink."""

    path.parent.mkdir(parents=True, exist_ok=True)
    target_mode: int | None = None
    try:
        target_stat = path.lstat()
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISREG(target_stat.st_mode):
            target_mode = stat.S_IMODE(target_stat.st_mode)

    temporary_path: Path | None = None
    descriptor: int | None = None
    try:
        for _ in range(100):
            temporary_path = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
            try:
                descriptor = os.open(
                    temporary_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o666,
                )
                break
            except FileExistsError:
                continue
        else:
            raise FileExistsError(f"failed to create temporary file for: {path}")

        if target_mode is not None and hasattr(os, "fchmod"):
            os.fchmod(descriptor, target_mode)
        with os.fdopen(descriptor, "w", encoding=encoding) as temporary:
            descriptor = None
            temporary.write(content)
        os.replace(temporary_path, path)
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:  # pragma: no branch - assigned before every I/O attempt
            temporary_path.unlink(missing_ok=True)
        raise
