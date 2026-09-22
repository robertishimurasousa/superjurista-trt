#!/usr/bin/env python3
"""Rehearse the real macOS Python, MCP, Poppler, and Portuguese OCR stack."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_PACKAGES = {
    "beautifulsoup4",
    "mcp",
    "pdf2image",
    "pdfplumber",
    "pytesseract",
    "PyPDF2",
    "pyotp",
    "requests",
    "urllib3",
}
REQUIRED_EXECUTABLES = {"pdftoppm", "tesseract"}
EXPECTED_MCP_SERVERS = {
    "bnp-api",
    "cjf-jurisprudencia",
    "tcu-jurisprudencia",
    "tjsc-eproc",
    "tnu-eproc",
}
REQUIRED_OCR_PHRASES = {
    "JUSTIÇA DO TRABALHO",
    "Horas extras reconhecidas",
}
EVIDENCE_FIELDS = {
    "python_version",
    "packages",
    "executables",
    "tesseract_languages",
    "mcp_servers",
    "ocr",
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class HostRehearsalError(ValueError):
    """Raised when target-host evidence is incomplete or incompatible."""


def assess_host_evidence(evidence: object) -> dict:
    """Validate collected evidence and return a deterministic readiness summary."""
    if not isinstance(evidence, dict):
        raise HostRehearsalError("host evidence must be an object")
    unknown = set(evidence) - EVIDENCE_FIELDS
    missing = EVIDENCE_FIELDS - set(evidence)
    if unknown:
        raise HostRehearsalError("unknown host evidence field: " + sorted(unknown)[0])
    if missing:
        raise HostRehearsalError("missing host evidence field: " + sorted(missing)[0])

    python_version = _version_tuple(evidence["python_version"], "python_version")
    if python_version < (3, 10):
        raise HostRehearsalError("python_version must be 3.10 or newer")
    packages = evidence["packages"]
    if not isinstance(packages, dict):
        raise HostRehearsalError("packages must be an object")
    package_names = set(packages)
    if package_names != REQUIRED_PACKAGES:
        absent = sorted(REQUIRED_PACKAGES - package_names)
        extra = sorted(package_names - REQUIRED_PACKAGES)
        name = absent[0] if absent else extra[0]
        raise HostRehearsalError(f"package evidence is incomplete: {name}")
    for name, version in packages.items():
        _version_tuple(version, name)
    if _version_tuple(packages["mcp"], "mcp")[0] != 1:
        raise HostRehearsalError("mcp package must remain on supported major version 1")

    executables = evidence["executables"]
    if not isinstance(executables, dict) or set(executables) != REQUIRED_EXECUTABLES:
        raise HostRehearsalError("executable evidence is incomplete")
    for name in sorted(REQUIRED_EXECUTABLES):
        record = executables[name]
        if not isinstance(record, dict) or set(record) != {"available", "version"}:
            raise HostRehearsalError(f"{name} executable evidence is invalid")
        if record["available"] is not True:
            raise HostRehearsalError(f"{name} executable is unavailable")
        _version_tuple(record["version"], name)

    languages = evidence["tesseract_languages"]
    if not isinstance(languages, list) or any(not isinstance(item, str) for item in languages):
        raise HostRehearsalError("Tesseract language evidence is invalid")
    if "por" not in languages:
        raise HostRehearsalError("Portuguese Tesseract language data is unavailable")
    if languages != sorted(set(languages)):
        raise HostRehearsalError("Tesseract languages must be unique and sorted")

    servers = evidence["mcp_servers"]
    if not isinstance(servers, list) or set(servers) != EXPECTED_MCP_SERVERS:
        raise HostRehearsalError("MCP server rehearsal is incomplete")
    if servers != sorted(set(servers)):
        raise HostRehearsalError("MCP server evidence must be unique and sorted")

    ocr = evidence["ocr"]
    if not isinstance(ocr, dict) or set(ocr) != {
        "pages",
        "recognized_phrases",
        "text_sha256",
    }:
        raise HostRehearsalError("OCR evidence is invalid")
    if ocr["pages"] != 1:
        raise HostRehearsalError("OCR rehearsal must process exactly one page")
    phrases = ocr["recognized_phrases"]
    if not isinstance(phrases, list) or set(phrases) != REQUIRED_OCR_PHRASES:
        raise HostRehearsalError("OCR phrase coverage is incomplete")
    if phrases != sorted(set(phrases)):
        raise HostRehearsalError("OCR phrases must be unique and sorted")
    if not isinstance(ocr["text_sha256"], str) or not SHA256_PATTERN.fullmatch(
        ocr["text_sha256"]
    ):
        raise HostRehearsalError("OCR text digest is invalid")

    digest = hashlib.sha256(
        json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "status": "ready",
        "python_version": evidence["python_version"],
        "mcp_version": packages["mcp"],
        "mcp_server_count": len(servers),
        "ocr_pages": ocr["pages"],
        "evidence_digest": digest,
    }


def collect_host_evidence(root: Path) -> dict:
    """Execute the installed stack and collect secret-free readiness evidence."""
    if not isinstance(root, Path) or not root.is_dir():
        raise HostRehearsalError("repository root must be an existing directory")
    packages = {}
    for name in sorted(REQUIRED_PACKAGES):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise HostRehearsalError(f"required package is unavailable: {name}") from error

    executables = {}
    for name, version_args in (("pdftoppm", ("-v",)), ("tesseract", ("--version",))):
        path = shutil.which(name)
        if path is None:
            raise HostRehearsalError(f"{name} executable is unavailable")
        output = _run_command((path, *version_args))
        executables[name] = {
            "available": True,
            "version": _first_version(output, name),
        }

    tesseract_path = shutil.which("tesseract")
    language_output = _run_command((tesseract_path, "--list-langs"))
    languages = sorted(
        line.strip()
        for line in language_output.splitlines()
        if re.fullmatch(r"[a-z][a-z0-9_]*", line.strip())
    )
    servers = _rehearse_mcp_servers(root)
    ocr = _rehearse_ocr(root)
    return {
        "python_version": ".".join(str(item) for item in sys.version_info[:3]),
        "packages": packages,
        "executables": executables,
        "tesseract_languages": languages,
        "mcp_servers": servers,
        "ocr": ocr,
    }


def _rehearse_mcp_servers(root: Path) -> list[str]:
    server_paths = sorted((root / "scaffold" / "mcp-servers").glob("*/server.py"))
    loaded = []
    for index, path in enumerate(server_paths):
        spec = importlib.util.spec_from_file_location(f"_host_mcp_{index}", path)
        if spec is None or spec.loader is None:
            raise HostRehearsalError(f"MCP server cannot be loaded: {path.parent.name}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            raise HostRehearsalError(
                f"MCP server import failed: {path.parent.name}: {type(error).__name__}"
            ) from error
        if getattr(module, "mcp", None) is None:
            raise HostRehearsalError(f"MCP server object is missing: {path.parent.name}")
        loaded.append(path.parent.name)
    return loaded


def _rehearse_ocr(root: Path) -> dict:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        raise HostRehearsalError("Pillow is unavailable for the OCR rehearsal") from error
    converter_path = root / "scaffold" / "skills" / "converter-pdf" / "scripts" / "pdf_para_txt.py"
    spec = importlib.util.spec_from_file_location("_host_pdf_converter", converter_path)
    if spec is None or spec.loader is None:
        raise HostRehearsalError("preserved PDF converter cannot be loaded")
    converter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(converter)

    with tempfile.TemporaryDirectory(prefix="superjurista-trt-host-") as directory:
        workspace = Path(directory).resolve()
        image = Image.new("RGB", (1800, 900), "white")
        draw = ImageDraw.Draw(image)
        font_path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
        if not font_path.is_file():
            raise HostRehearsalError("macOS Arial font is unavailable for OCR rehearsal")
        font = ImageFont.truetype(str(font_path), 92)
        draw.multiline_text(
            (110, 150),
            "JUSTIÇA DO TRABALHO\nHoras extras reconhecidas",
            fill="black",
            font=font,
            spacing=45,
        )
        pdf_path = workspace / "rehearsal.pdf"
        image.save(pdf_path, "PDF", resolution=300.0)
        try:
            text, pages = converter.extrair_texto_ocr(str(pdf_path))
        except Exception as error:
            raise HostRehearsalError(
                f"preserved PDF OCR rehearsal failed: {type(error).__name__}"
            ) from error
    normalized = " ".join(text.split())
    recognized = sorted(
        phrase for phrase in REQUIRED_OCR_PHRASES if phrase in normalized
    )
    return {
        "pages": pages,
        "recognized_phrases": recognized,
        "text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }


def _run_command(arguments: tuple[str, ...]) -> str:
    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        raise HostRehearsalError(f"host command failed: {Path(arguments[0]).name}")
    return output


def _first_version(output: str, label: str) -> str:
    match = re.search(r"\b([0-9]+(?:\.[0-9]+){1,3})\b", output)
    if match is None:
        raise HostRehearsalError(f"{label} version could not be identified")
    return match.group(1)


def _version_tuple(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", value) is None:
        raise HostRehearsalError(f"{label} version is invalid")
    return tuple(int(part) for part in value.split("."))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        report = assess_host_evidence(collect_host_evidence(arguments.root.resolve()))
    except HostRehearsalError as error:
        print(f"[ERROR] target-host rehearsal: {error}", file=sys.stderr)
        return 1
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(serialized, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
        print(f"[OK] target-host rehearsal: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
