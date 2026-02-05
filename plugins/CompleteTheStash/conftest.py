import tempfile
from pathlib import Path

import pytest
import yaml
from stashapi import log
from stashapi.stashapp import StashInterface
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

from test_helpers import (
    POSTGRES_IMAGE,
    STASH_INTERNAL_PORT,
    STASHBOX_IMAGE,
    STASHBOX_INTERNAL_PORT,
    capture_stashbox_api_key,
    copy_files_to_plugin_directory,
    create_manifest_file,
    create_stash_container,
    local_stash_api_key,
    make_config_paths_absolute,
    missing_stash_api_key,
    wait_for_postgres_ready,
    wait_for_stash_ready,
    wait_for_stashbox_ready,
)


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


@pytest.fixture(scope="module")
def local_stash_instance(stash_network, stashbox_instance):
    """Local stash instance with CompleteTheStash plugin configured for local stashbox."""
    test_dir = Path(__file__).resolve().parent
    template_dir = test_dir / ".template-stash"
    config_dir = Path(tempfile.mkdtemp())
    plugin_dir = config_dir / "plugins" / "CompleteTheStash"
    local_config_path = template_dir / "local-config.txt"

    with local_config_path.open() as file:
        local_config = yaml.safe_load(file)

    local_config["api_key"] = local_stash_api_key
    local_config["port"] = STASH_INTERNAL_PORT

    # Configure stash_boxes to point to local stashbox
    local_config["stash_boxes"] = [{
        "name": "Local StashBox",
        "endpoint": f"http://stashbox:{STASHBOX_INTERNAL_PORT}/graphql",
        "apikey": stashbox_instance["api_key"],
    }]

    # Configure plugin settings
    local_config["plugins"]["settings"]["CompleteTheStash"] = {
        "performerTags": "Completionist",
        "sceneExcludeTags": "Compilation",
        "missingStashAddress": f"http://missing-stash:{STASH_INTERNAL_PORT}",
        "missingStashApiKey": missing_stash_api_key,
    }

    make_config_paths_absolute(local_config)
    with (config_dir / "config.yml").open("w") as file:
        yaml.safe_dump(local_config, file)

    # Copy plugin files
    excluded_files = {".gitignore", "stash-macos", ".template-stash"}
    files_copied = copy_files_to_plugin_directory(test_dir, plugin_dir, excluded_files)
    create_manifest_file(plugin_dir, files_copied)

    # Set STASHDB_ENDPOINT env var to match local stashbox
    env_vars = {
        "STASHDB_ENDPOINT": f"http://stashbox:{STASHBOX_INTERNAL_PORT}/graphql"
    }

    container = create_stash_container(config_dir, stash_network, env_vars=env_vars)
    container.start()
    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(STASH_INTERNAL_PORT))
    wait_for_stash_ready(host, port, api_key=local_stash_api_key)

    interface = StashInterface({
        "scheme": "http",
        "host": host,
        "port": port,
        "logger": log,
        "ApiKey": local_stash_api_key,
    })

    # Store connection info as attributes for direct plugin execution tests
    interface._test_scheme = "http"
    interface._test_host = host
    interface._test_port = port
    interface._test_api_key = local_stash_api_key

    yield interface

    container.stop()


@pytest.fixture(scope="module")
def missing_stash_instance(stash_network, stashbox_instance):
    """Missing stash instance to receive missing scenes."""
    test_dir = Path(__file__).resolve().parent
    template_dir = test_dir / ".template-stash"
    config_dir = Path(tempfile.mkdtemp())
    missing_config_path = template_dir / "missing-stashdb-config.txt"

    with missing_config_path.open() as file:
        missing_config = yaml.safe_load(file)

    missing_config["api_key"] = missing_stash_api_key
    missing_config["port"] = STASH_INTERNAL_PORT

    # Configure stash_boxes to point to local stashbox
    missing_config["stash_boxes"] = [{
        "name": "Local StashBox",
        "endpoint": f"http://stashbox:{STASHBOX_INTERNAL_PORT}/graphql",
        "apikey": stashbox_instance["api_key"],
    }]

    make_config_paths_absolute(missing_config)
    with (config_dir / "config.yml").open("w") as file:
        yaml.safe_dump(missing_config, file)

    container = create_stash_container(config_dir, stash_network, network_alias="missing-stash")
    container.start()
    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(STASH_INTERNAL_PORT))
    wait_for_stash_ready(host, port, api_key=missing_stash_api_key)

    interface = StashInterface({
        "scheme": "http",
        "host": host,
        "port": port,
        "apikey": missing_stash_api_key,
        "logger": log,
    })

    # Store connection info as attributes for direct plugin execution tests
    interface._test_scheme = "http"
    interface._test_host = host
    interface._test_port = port
    interface._test_api_key = missing_stash_api_key

    yield interface

    container.stop()
