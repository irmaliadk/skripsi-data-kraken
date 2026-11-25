"""Periksa versi Git yang menjalankan eksperimen."""

import subprocess

from src.inti_skripsi.data import ROOT


def commit_eksperimen():
    """Kembalikan SHA setelah memeriksa kode dan data penelitian setempat."""
    try:
        status = subprocess.check_output(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                "src",
                "scripts",
                "data/raw",
                ".github/workflows",
            ],
            cwd=ROOT,
            text=True,
        )
        if status.strip():
            raise ValueError(
                "Simpan perubahan kode dan data penelitian dalam commit Git"
            )
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("Versi Git untuk eksperimen tidak dapat diperiksa") from exc
