import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network


STASHBOX_IMAGE = "stashapp/stash-box:development"
STASHBOX_INTERNAL_PORT = 9998
POSTGRES_IMAGE = "postgres:17.2"


def wait_for_postgres_ready(container, timeout=60, poll_interval=0.5):
    """Wait for PostgreSQL to be ready to accept connections."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        logs = container.get_logs()[0].decode("utf-8")
        if "database system is ready to accept connections" in logs:
            return True
        time.sleep(poll_interval)
    raise TimeoutError(f"PostgreSQL did not become ready within {timeout}s")


def capture_stashbox_api_key(container, timeout=60, poll_interval=0.5):
    """Capture the root API key from stashbox startup logs."""
    start_time = time.time()
    pattern = re.compile(r"API Key:\s+(\S+)")

    while time.time() - start_time < timeout:
        logs = container.get_logs()[0].decode("utf-8")
        match = pattern.search(logs)
        if match:
            return match.group(1)
        time.sleep(poll_interval)

    raise TimeoutError(f"Failed to capture API key from stashbox logs within {timeout}s")


def wait_for_stashbox_ready(host, port, api_key, timeout=60, poll_interval=0.5):
    """Wait for stash-box to be ready to accept GraphQL requests."""
    url = f"http://{host}:{port}/graphql"
    query = '{"query":"{ version { version } }"}'
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            headers = {
                "Content-Type": "application/json",
                "ApiKey": api_key,
            }
            req = urllib.request.Request(
                url,
                data=query.encode("utf-8"),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError):
            pass
        time.sleep(poll_interval)

    raise TimeoutError(f"Stash-box at {url} did not become ready within {timeout}s")


@pytest.fixture(scope="module")
def stash_network():
    with Network() as network:
        yield network


@pytest.fixture(scope="module")
def stashbox_postgres(stash_network):
    """PostgreSQL database for stash-box."""
    container = (
        DockerContainer(POSTGRES_IMAGE)
        .with_env("POSTGRES_USER", "stashbox")
        .with_env("POSTGRES_PASSWORD", "stashbox")
        .with_env("POSTGRES_DB", "stashbox")
        .with_network(stash_network)
        .with_network_aliases("stashbox-postgres")
    )
    container.start()
    wait_for_postgres_ready(container)
    yield container
    container.stop()


@pytest.fixture(scope="module")
def stashbox_instance(stash_network, stashbox_postgres):
    """Local stash-box instance for testing."""
    # Create config directory
    config_dir = Path(tempfile.mkdtemp())

    # Create stash-box config file
    config_content = {
        "database": "stashbox:stashbox@stashbox-postgres:5432/stashbox?sslmode=disable",
        "require_invite": False,
        "is_production": False,
        "default_user_roles": ["READ", "VOTE", "EDIT", "MODIFY", "ADMIN"],
    }

    with (config_dir / "stash-box-config.yml").open("w") as f:
        yaml.safe_dump(config_content, f)

    # Start stash-box container
    container = (
        DockerContainer(STASHBOX_IMAGE)
        .with_volume_mapping(str(config_dir), "/root/.stash-box", "rw")
        .with_exposed_ports(STASHBOX_INTERNAL_PORT)
        .with_network(stash_network)
        .with_network_aliases("stashbox")
    )
    container.start()

    # Capture API key from logs
    api_key = capture_stashbox_api_key(container)

    # Wait for stash-box to be ready
    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(STASHBOX_INTERNAL_PORT))
    wait_for_stashbox_ready(host, port, api_key)

    yield {
        "container": container,
        "host": host,
        "port": port,
        "api_key": api_key,
        "endpoint": f"http://{host}:{port}/graphql",
    }

    container.stop()


def test_stashbox_basic_query(stashbox_instance):
    """Test that we can query the stashbox instance."""
    url = stashbox_instance["endpoint"]
    api_key = stashbox_instance["api_key"]

    # Query version
    query = '{"query":"{ version { version } }"}'
    headers = {
        "Content-Type": "application/json",
        "ApiKey": api_key,
    }

    req = urllib.request.Request(
        url,
        data=query.encode("utf-8"),
        headers=headers,
    )

    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        body = response.read().decode("utf-8")
        assert "version" in body


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
