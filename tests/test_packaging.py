from pathlib import Path
import tomllib


def test_vercel_and_pip_install_the_same_runtime_dependencies():
    root = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((root / "pyproject.toml").read_text())
    requirements = {
        line.strip() for line in (root / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert set(manifest["project"]["dependencies"]) == requirements
    assert manifest["tool"]["uv"]["package"] is False
