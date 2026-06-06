from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from bot.config import settings

logger = logging.getLogger(__name__)


async def convert_to_pdf(docx_path: Path) -> Path | None:
    """Convert a .docx to .pdf via LibreOffice headless. Returns None on any failure."""
    if not settings.pdf_export_enabled:
        return None
    if not docx_path.exists():
        logger.warning("PDF conversion skipped, file not found: %s", docx_path)
        return None

    outdir = docx_path.parent
    # Isolated profile dir so concurrent conversions don't fight over LibreOffice's lock.
    profile_dir = Path(tempfile.mkdtemp(prefix="lo_profile_"))
    try:
        process = await asyncio.create_subprocess_exec(
            settings.libreoffice_binary,
            f"-env:UserInstallation=file://{profile_dir}",
            "--headless",
            "--nologo",
            "--nolockcheck",
            "--convert-to",
            "pdf",
            "--outdir",
            str(outdir),
            str(docx_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("LibreOffice binary not found: %s (install libreoffice)", settings.libreoffice_binary)
        shutil.rmtree(profile_dir, ignore_errors=True)
        return None

    try:
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.pdf_export_timeout_seconds,
            )
        except asyncio.TimeoutError:
            process.kill()
            logger.error("PDF conversion timed out for %s", docx_path)
            return None

        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="replace")[-800:]
            logger.error("LibreOffice PDF conversion failed (code %s): %s", process.returncode, error_text)
            return None

        pdf_path = outdir / f"{docx_path.stem}.pdf"
        if not pdf_path.exists():
            logger.error("LibreOffice reported success but PDF is missing: %s", pdf_path)
            return None
        return pdf_path
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)
