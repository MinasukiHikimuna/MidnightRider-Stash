import json
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


class StashBoxClient:
    """GraphQL client for seeding test data in stash-box."""

    def __init__(self, endpoint, api_key):
        self.endpoint = endpoint
        self.api_key = api_key

    def _execute_query(self, query, variables=None):
        """Execute a GraphQL query against stash-box."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        headers = {
            "Content-Type": "application/json",
            "ApiKey": self.api_key,
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "errors" in result:
                raise Exception(f"GraphQL error: {result['errors']}")
            return result.get("data")

    def create_tag(self, name):
        """Create a tag and return its ID."""
        query = """
        mutation CreateTag($input: TagCreateInput!) {
            tagCreate(input: $input) {
                id
                name
            }
        }
        """
        variables = {"input": {"name": name}}
        data = self._execute_query(query, variables)
        return data["tagCreate"]["id"]

    def create_performer(self, name, gender="FEMALE"):
        """Create a performer and return its ID."""
        query = """
        mutation CreatePerformer($input: PerformerCreateInput!) {
            performerCreate(input: $input) {
                id
                name
                gender
            }
        }
        """
        variables = {"input": {"name": name, "gender": gender}}
        data = self._execute_query(query, variables)
        return data["performerCreate"]["id"]

    def create_studio(self, name, parent_id=None):
        """Create a studio and return its ID."""
        query = """
        mutation CreateStudio($input: StudioCreateInput!) {
            studioCreate(input: $input) {
                id
                name
            }
        }
        """
        variables = {"input": {"name": name}}
        if parent_id:
            variables["input"]["parent_id"] = parent_id
        data = self._execute_query(query, variables)
        return data["studioCreate"]["id"]

    def create_scene(self, title, date, performer_ids=None, studio_id=None, tag_ids=None):
        """Create a scene and return its ID."""
        query = """
        mutation CreateScene($input: SceneCreateInput!) {
            sceneCreate(input: $input) {
                id
                title
                date
            }
        }
        """
        variables = {
            "input": {
                "title": title,
                "date": date,
                "fingerprints": [],  # Required field
            }
        }
        if performer_ids:
            variables["input"]["performers"] = [
                {"performer_id": pid} for pid in performer_ids
            ]
        if studio_id:
            variables["input"]["studio_id"] = studio_id
        if tag_ids:
            variables["input"]["tag_ids"] = tag_ids

        data = self._execute_query(query, variables)
        return data["sceneCreate"]["id"]

    def query_scenes(self):
        """Query all scenes."""
        query = """
        query QueryScenes {
            queryScenes(input: {}) {
                scenes {
                    id
                    title
                    date
                    studio { id name }
                    performers { performer { id name } }
                    tags { id name }
                }
                count
            }
        }
        """
        data = self._execute_query(query)
        return data["queryScenes"]["scenes"]


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


def test_stashbox_seed_and_query(stashbox_instance):
    """Test that we can seed data and query it back."""
    client = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )

    # Create test data
    tag_id = client.create_tag("Compilation")
    performer_id = client.create_performer("Luna Starling", "FEMALE")
    parent_studio_id = client.create_studio("Parent Network")
    studio_id = client.create_studio("Test Studio", parent_id=parent_studio_id)

    # Create scenes
    client.create_scene(
        title="Quality Work",
        date="2024-01-15",
        performer_ids=[performer_id],
        studio_id=studio_id
    )
    client.create_scene(
        title="Teamwork Vol 2",
        date="2024-04-05",
        performer_ids=[performer_id],
        studio_id=studio_id,
        tag_ids=[tag_id]
    )

    # Query scenes back
    scenes = client.query_scenes()
    assert len(scenes) == 2

    # Verify scene data
    scene_titles = {s["title"] for s in scenes}
    assert "Quality Work" in scene_titles
    assert "Teamwork Vol 2" in scene_titles

    # Verify scene has performer
    quality_work = next(s for s in scenes if s["title"] == "Quality Work")
    assert len(quality_work["performers"]) == 1
    assert quality_work["performers"][0]["performer"]["name"] == "Luna Starling"
    assert quality_work["studio"]["name"] == "Test Studio"

    # Verify compilation tag
    teamwork = next(s for s in scenes if s["title"] == "Teamwork Vol 2")
    assert len(teamwork["tags"]) == 1
    assert teamwork["tags"][0]["name"] == "Compilation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
