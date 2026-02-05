import subprocess
import sys


def test_imports() -> None:
    import mini_miloco  # noqa: F401
    import mini_miloco.auth  # noqa: F401
    import mini_miloco.http  # noqa: F401


def test_cli_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mini_miloco.auth", "--help"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert "OAuth" in result.stdout or "oauth" in result.stdout

    result = subprocess.run(
        [sys.executable, "-m", "mini_miloco.http", "--help"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert "HTTP" in result.stdout or "http" in result.stdout
