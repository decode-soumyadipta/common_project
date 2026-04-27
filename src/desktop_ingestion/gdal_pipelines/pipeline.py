from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import shutil
import subprocess
from typing import Sequence


@dataclass(frozen=True)
class GdalTranslateRequest:
    """Describes an idempotent gdal_translate operation."""

    source_path: Path
    target_path: Path
    output_format: str = "GTiff"
    creation_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineResult:
    """Result metadata for pipeline execution."""

    command: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str


def build_translate_command(request: GdalTranslateRequest) -> tuple[str, ...]:
    """Build a deterministic gdal_translate command for a raster conversion."""
    source = Path(request.source_path).expanduser().resolve()
    target = Path(request.target_path).expanduser().resolve()
    command: list[str] = [
        "gdal_translate",
        "-of",
        str(request.output_format),
    ]
    for option in request.creation_options:
        command.extend(["-co", str(option)])
    command.extend([str(source), str(target)])
    return tuple(command)


def command_as_shell(command: Sequence[str]) -> str:
    """Render a command as a shell-safe string for logs/UI."""
    return " ".join(shlex.quote(part) for part in command)


def run_translate_pipeline(request: GdalTranslateRequest) -> PipelineResult:
    """Run a GDAL translate pipeline with explicit error messaging."""
    command = build_translate_command(request)
    if shutil.which(command[0]) is None:
        raise RuntimeError(
            "gdal_translate is not available on PATH. Install GDAL to run desktop ingestion pipelines."
        )

    process = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    return PipelineResult(
        command=tuple(command),
        return_code=int(process.returncode),
        stdout=process.stdout or "",
        stderr=process.stderr or "",
    )
