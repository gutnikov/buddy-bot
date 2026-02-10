"""Tests for Docker deployment validation.

These tests verify the Docker image builds correctly and containers
can start with proper configuration.

These tests require Docker to be available on the host and are skipped
when running inside a container (no docker CLI).
"""

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="Docker CLI not available (likely running inside container)",
)


def _run(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )


def test_docker_build_succeeds():
    """Docker image builds without errors."""
    result = _run("docker build -t buddy-bot-test .", timeout=120)
    assert result.returncode == 0, f"Build failed: {result.stderr}"


def test_image_size_under_500mb():
    """Image size is reasonable (< 500MB)."""
    result = _run("docker images buddy-bot-test --format '{{.Size}}'")
    size_str = result.stdout.strip()
    # Parse size — could be "389MB" or "0.39GB"
    if "GB" in size_str:
        size_mb = float(size_str.replace("GB", "")) * 1024
    else:
        size_mb = float(size_str.replace("MB", ""))
    assert size_mb < 500, f"Image is {size_mb}MB, expected < 500MB"


def test_container_starts_and_shows_help():
    """Container can start and run Python successfully."""
    result = _run(
        "docker run --rm buddy-bot-test python -c 'import buddy_bot; print(\"ok\")'"
    )
    assert result.returncode == 0
    assert "ok" in result.stdout


def test_environment_variables_accessible():
    """Environment variables are passed to the container."""
    result = _run(
        'docker run --rm -e TEST_VAR=hello buddy-bot-test python -c '
        '"import os; print(os.environ.get(\'TEST_VAR\', \'\'))"'
    )
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_data_volume_mount():
    """The /data directory exists and is writable."""
    result = _run(
        "docker run --rm buddy-bot-test sh -c "
        "'touch /data/test.txt && ls /data/test.txt'"
    )
    assert result.returncode == 0
    assert "test.txt" in result.stdout


def test_dockerignore_excludes_tests():
    """Tests directory should not be in the image (via .dockerignore)."""
    result = _run(
        "docker run --rm buddy-bot-test sh -c 'ls /app/tests 2>&1 || echo MISSING'"
    )
    assert "MISSING" in result.stdout or "No such file" in result.stdout
