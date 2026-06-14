from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path

from bot.config import settings

logger = logging.getLogger(__name__)

# Explicit export filters are more reliable for headless conversion than the bare "pdf".
_FILTERS = {
    ".pptx": "pdf:impress_pdf_Export",
    ".ppt": "pdf:impress_pdf_Export",
    ".docx": "pdf:writer_pdf_Export",
    ".doc": "pdf:writer_pdf_Export",
}

_OUTPUT_RE = re.compile(r"->\s*(.+?\.pdf)", re.IGNORECASE)


async def convert_to_pdf(source_path: Path) -> Path | None:
    """Convert a document to PDF via LibreOffice headless. Returns None on any failure."""
    if not settings.pdf_export_enabled:
        return None
    source = source_path.resolve()
    if not source.exists():
        logger.warning("PDF conversion skipped, file not found: %s", source)
        return None

    # First run of a fresh impress profile can silently produce nothing; retry once.
    for attempt in (1, 2):
        pdf_path = await _run_soffice(source)
        if pdf_path is not None:
            return pdf_path
        logger.warning("PDF conversion attempt %s produced no file for %s", attempt, source)
    return None


async def _run_soffice(source: Path) -> Path | None:
    outdir = source.parent
    convert_filter = _FILTERS.get(source.suffix.lower(), "pdf")
    profile_dir = Path(tempfile.mkdtemp(prefix="lo_profile_"))
    try:
        process = await asyncio.create_subprocess_exec(
            settings.libreoffice_binary,
            f"-env:UserInstallation=file://{profile_dir}",
            "--headless",
            "--nologo",
            "--nolockcheck",
            "--norestore",
            "--convert-to",
            convert_filter,
            "--outdir",
            str(outdir),
            str(source),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("LibreOffice binary not found: %s (install libreoffice)", settings.libreoffice_binary)
        shutil.rmtree(profile_dir, ignore_errors=True)
        return None

    try:
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.pdf_export_timeout_seconds,
            )
        except asyncio.TimeoutError:
            process.kill()
            logger.error("PDF conversion timed out for %s", source)
            return None

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if process.returncode != 0:
            logger.error("LibreOffice failed (code %s): %s", process.returncode, (stderr or stdout)[-800:])
            return None

        # Prefer the path LibreOffice printed, then the expected name, then any fresh pdf.
        match = _OUTPUT_RE.search(stdout)
        if match:
            reported = Path(match.group(1).strip())
            if reported.exists():
                return reported

        expected = outdir / f"{source.stem}.pdf"
        if expected.exists():
            return expected

        candidates = sorted(outdir.glob(f"{source.stem}*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            return candidates[0]

        logger.error(
            "LibreOffice returned 0 but no PDF found for %s. stdout=%s stderr=%s",
            source,
            stdout[-400:],
            stderr[-400:],
        )
        return None
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)
