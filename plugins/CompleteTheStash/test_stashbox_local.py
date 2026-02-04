import json
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from stashapi import log
from stashapi.stashapp import StashInterface
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network


STASHBOX_IMAGE = "stashapp/stash-box:development"
STASHBOX_INTERNAL_PORT = 9998
POSTGRES_IMAGE = "postgres:17.2"
STASH_IMAGE = "stashapp/stash:latest"
STASH_INTERNAL_PORT = 9999
STASH_CONFIG_DIR = "/root/.stash"
RELATIVE_PATH_KEYS = ["blobs_path", "cache", "database", "generated", "plugins_path", "scrapers_path"]

# API keys for test stash instances
local_stash_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ0ZXN0Iiwic3ViIjoiQVBJS2V5IiwiaWF0IjoxNzM4NzAwMDAwfQ.test_local_stash"  # noqa: E501
missing_stash_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ0ZXN0Iiwic3ViIjoiQVBJS2V5IiwiaWF0IjoxNzM4NzAwMDAxfQ.test_missing_stash"  # noqa: E501


class PerformerBuilder:
    """Builder for test performer data."""

    def __init__(self, name, gender="FEMALE"):
        self.name = name
        self.gender = gender
        self.stashbox_id = None
        self.stash_endpoint = None

    def with_stashbox_id(self, stashbox_id, endpoint):
        """Set the stashbox ID after seeding."""
        self.stashbox_id = stashbox_id
        self.stash_endpoint = endpoint
        return self

    def for_stashbox_create(self):
        """Get input for StashBoxClient.create_performer()."""
        return {
            "name": self.name,
            "gender": self.gender,
        }

    def for_stash_create(self, tag_ids=None):
        """Get input for StashInterface.create_performer()."""
        data = {
            "name": self.name,
            "gender": self.gender,
        }
        if self.stashbox_id and self.stash_endpoint:
            data["stash_ids"] = [{
                "stash_id": self.stashbox_id,
                "endpoint": self.stash_endpoint,
            }]
        if tag_ids:
            data["tag_ids"] = tag_ids
        return data


class SceneBuilder:
    """Builder for test scene data."""

    def __init__(self, title, date):
        self.title = title
        self.date = date
        self.stashbox_id = None
        self.stash_endpoint = None
        self.performer_ids = []
        self.studio_id = None
        self.tag_ids = []

    def with_stashbox_id(self, stashbox_id, endpoint):
        """Set the stashbox ID after seeding."""
        self.stashbox_id = stashbox_id
        self.stash_endpoint = endpoint
        return self

    def with_performers(self, *performer_ids):
        """Add performer IDs for stashbox creation."""
        self.performer_ids = list(performer_ids)
        return self

    def with_studio(self, studio_id):
        """Add studio ID for stashbox creation."""
        self.studio_id = studio_id
        return self

    def with_tags(self, *tag_ids):
        """Add tag IDs for stashbox creation."""
        self.tag_ids = list(tag_ids)
        return self

    def for_stashbox_create(self):
        """Get input for StashBoxClient.create_scene()."""
        return {
            "title": self.title,
            "date": self.date,
            "performer_ids": self.performer_ids if self.performer_ids else None,
            "studio_id": self.studio_id,
            "tag_ids": self.tag_ids if self.tag_ids else None,
        }

    def for_stash_create(self, performer_ids=None):
        """Get input for StashInterface.create_scene().

        Args:
            performer_ids: Optional list of local stash performer IDs (not stashbox IDs)
        """
        data = {"title": self.title}
        if self.stashbox_id and self.stash_endpoint:
            data["stash_ids"] = [{
                "stash_id": self.stashbox_id,
                "endpoint": self.stash_endpoint,
            }]
        if performer_ids:
            data["performer_ids"] = performer_ids
        return data


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
        try:
            data = self._execute_query(query, variables)
            return data["tagCreate"]["id"]
        except Exception as e:
            # Tag might already exist, try to find it
            if "duplicate key" in str(e):
                return self.find_tag_by_name(name)
            raise

    def find_tag_by_name(self, name):
        """Find a tag by name and return its ID."""
        query = """
        query QueryTags($input: TagQueryInput!) {
            queryTags(input: $input) {
                tags {
                    id
                    name
                }
            }
        }
        """
        variables = {"input": {"names": name}}
        data = self._execute_query(query, variables)
        tags = data["queryTags"]["tags"]
        if tags:
            return tags[0]["id"]
        raise Exception(f"Tag '{name}' not found")

    def create_performer(self, performer):
        """Create a performer from a PerformerBuilder and return its ID.

        Also updates the builder with the stashbox ID and endpoint.
        """
        if isinstance(performer, PerformerBuilder):
            input_data = performer.for_stashbox_create()
        else:
            # Support dict input for backward compatibility
            input_data = performer

        query = """
        mutation CreatePerformer($input: PerformerCreateInput!) {
            performerCreate(input: $input) {
                id
                name
                gender
            }
        }
        """
        variables = {"input": input_data}
        data = self._execute_query(query, variables)
        performer_id = data["performerCreate"]["id"]

        # Update builder with stashbox ID
        if isinstance(performer, PerformerBuilder):
            performer.with_stashbox_id(performer_id, self.endpoint)

        return performer_id

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

    def create_scene(self, scene):
        """Create a scene from a SceneBuilder and return its ID.

        Also updates the builder with the stashbox ID and endpoint.
        """
        if isinstance(scene, SceneBuilder):
            input_data = scene.for_stashbox_create()
        else:
            # Support dict input for backward compatibility
            input_data = scene

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
                "title": input_data["title"],
                "date": input_data["date"],
                "fingerprints": [],  # Required field
            }
        }
        if input_data.get("performer_ids"):
            variables["input"]["performers"] = [
                {"performer_id": pid} for pid in input_data["performer_ids"]
            ]
        if input_data.get("studio_id"):
            variables["input"]["studio_id"] = input_data["studio_id"]
        if input_data.get("tag_ids"):
            variables["input"]["tag_ids"] = input_data["tag_ids"]

        data = self._execute_query(query, variables)
        scene_id = data["sceneCreate"]["id"]

        # Update builder with stashbox ID
        if isinstance(scene, SceneBuilder):
            scene.with_stashbox_id(scene_id, self.endpoint)

        return scene_id

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


def make_config_paths_absolute(config):
    """Rewrite relative path fields to absolute paths under /root/.stash."""
    for key in RELATIVE_PATH_KEYS:
        if key in config and not str(config[key]).startswith("/"):
            config[key] = f"{STASH_CONFIG_DIR}/{config[key]}"


def create_stash_container(config_dir, network, network_alias=None, env_vars=None):
    """Create a stash container with the given config."""
    container = (
        DockerContainer(STASH_IMAGE)
        .with_volume_mapping(str(config_dir), "/root/.stash", "rw")
        .with_exposed_ports(STASH_INTERNAL_PORT)
        .with_env("STASH_PORT", str(STASH_INTERNAL_PORT))
        .with_network(network)
    )
    if network_alias:
        container.with_network_aliases(network_alias)
    if env_vars:
        for key, value in env_vars.items():
            container.with_env(key, value)
    return container


def wait_for_stash_ready(host, port, api_key=None, timeout=60, poll_interval=0.5):
    """Wait for Stash to be ready to accept connections."""
    url = f"http://{host}:{port}/graphql"
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["ApiKey"] = api_key
            req = urllib.request.Request(
                url,
                data=b'{"query":"{ systemStatus { status } }"}',
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError):
            pass
        time.sleep(poll_interval)
    raise TimeoutError(f"Stash at {url} did not become ready within {timeout}s")


def copy_files_to_plugin_directory(source_dir, target_dir, excluded_files):
    """Copy plugin files to the target directory."""
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)

    files_copied = []
    for entry in Path(source_dir).iterdir():
        if entry.name not in excluded_files and not entry.name.startswith("test_") and entry.is_file():
            shutil.copy(entry, target_dir)
            files_copied.append(entry.name)

    return files_copied


def create_manifest_file(target_dir, files_copied):
    """Create a manifest.yml file for the plugin."""
    manifest_content = {
        "id": "CompleteTheStash",
        "name": "CompleteTheStash",
        "metadata": {
            "description": (
                "Finds missing scenes for selected performers and creates "
                "missing scene metadata to another missing Stash instance."
            ),
            "version": "0.0.0-test",
            "date": datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "requires": [],
            "source_repository": "https://minasukihikimuna.github.io/MidnightRider-Stash/index.yml",
        },
        "files": files_copied,
    }

    with (Path(target_dir) / "manifest.yml").open("w") as file:
        yaml.safe_dump(manifest_content, file)


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

    yield StashInterface({
        "scheme": "http",
        "host": host,
        "port": port,
        "logger": log,
        "ApiKey": local_stash_api_key,
    })

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

    yield StashInterface({
        "scheme": "http",
        "host": host,
        "port": port,
        "apikey": missing_stash_api_key,
        "logger": log,
    })

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


def find_scene_by_stash_id(stash_instance, stash_id, endpoint):
    """Find a scene by its stash_id and endpoint."""
    return stash_instance.find_scenes({
        "stash_id_endpoint": {
            "endpoint": endpoint,
            "stash_id": stash_id,
            "modifier": "EQUALS",
        }
    })


def verify_scene_exists(stash_instance, scene_builder):
    """Verify a scene exists in stash with the expected data."""
    scenes = find_scene_by_stash_id(
        stash_instance,
        scene_builder.stashbox_id,
        scene_builder.stash_endpoint
    )
    assert len(scenes) == 1, f"Expected 1 scene, found {len(scenes)}"

    scene = scenes[0]
    assert scene["title"].upper() == scene_builder.title.upper()
    assert scene_builder.stashbox_id in [s["stash_id"] for s in scene["stash_ids"]]
    return scene


def verify_scene_not_exists(stash_instance, scene_builder):
    """Verify a scene does not exist in stash."""
    scenes = find_scene_by_stash_id(
        stash_instance,
        scene_builder.stashbox_id,
        scene_builder.stash_endpoint
    )
    assert len(scenes) == 0, f"Expected 0 scenes, found {len(scenes)}"


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
    """Test that we can seed data and query it back using builders."""
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )

    # Build test data
    tag_id = stashbox.create_tag("Compilation")
    performer = PerformerBuilder("Luna Starling", "FEMALE")
    parent_studio_id = stashbox.create_studio("Parent Network")
    studio_id = stashbox.create_studio("Test Studio", parent_id=parent_studio_id)

    # Seed performer to stashbox (updates builder with ID automatically)
    stashbox.create_performer(performer)

    # Build scenes
    quality_work = (SceneBuilder("Quality Work", "2024-01-15")
                    .with_performers(performer.stashbox_id)
                    .with_studio(studio_id))
    teamwork_vol_2 = (SceneBuilder("Teamwork Vol 2", "2024-04-05")
                      .with_performers(performer.stashbox_id)
                      .with_studio(studio_id)
                      .with_tags(tag_id))

    # Seed scenes to stashbox (updates builders with IDs automatically)
    stashbox.create_scene(quality_work)
    stashbox.create_scene(teamwork_vol_2)

    # Query scenes back
    scenes = stashbox.query_scenes()
    assert len(scenes) == 2

    # Verify scene data using builders
    scene_titles = {s["title"] for s in scenes}
    assert quality_work.title in scene_titles
    assert teamwork_vol_2.title in scene_titles

    # Verify scene has performer
    quality_work_data = next(s for s in scenes if s["title"] == quality_work.title)
    assert len(quality_work_data["performers"]) == 1
    assert quality_work_data["performers"][0]["performer"]["name"] == performer.name
    assert quality_work_data["studio"]["name"] == "Test Studio"

    # Verify compilation tag
    teamwork_data = next(s for s in scenes if s["title"] == teamwork_vol_2.title)
    assert len(teamwork_data["tags"]) == 1
    assert teamwork_data["tags"][0]["name"] == "Compilation"


def test_e2e_with_local_stashbox(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """End-to-end test: seed stashbox, run plugin, verify missing scenes are created."""
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )

    # Use internal endpoint for stash_ids (what containers see)
    internal_endpoint = f"http://stashbox:{STASHBOX_INTERNAL_PORT}/graphql"

    # Build test data
    compilation_tag_id = stashbox.create_tag("Compilation")
    performer = PerformerBuilder("Aria Phoenix", "FEMALE")
    studio_id = stashbox.create_studio("E2E Test Studio")

    # Seed performer to stashbox
    stashbox.create_performer(performer)
    # Override endpoint to internal network address
    performer.stash_endpoint = internal_endpoint

    # Build and seed scenes
    quality_work = (SceneBuilder("Quality Work", "2024-01-15")
                    .with_performers(performer.stashbox_id)
                    .with_studio(studio_id))
    gimme_all = (SceneBuilder("Gimme All", "2024-03-10")
                 .with_performers(performer.stashbox_id)
                 .with_studio(studio_id))
    teamwork_vol_2 = (SceneBuilder("Teamwork Vol 2", "2024-04-05")
                      .with_performers(performer.stashbox_id)
                      .with_studio(studio_id)
                      .with_tags(compilation_tag_id))

    stashbox.create_scene(quality_work)
    stashbox.create_scene(gimme_all)
    stashbox.create_scene(teamwork_vol_2)
    # Override endpoints to internal network address
    quality_work.stash_endpoint = internal_endpoint
    gimme_all.stash_endpoint = internal_endpoint
    teamwork_vol_2.stash_endpoint = internal_endpoint

    # Create completionist tag in local stash
    completionist_tag = local_stash_instance.create_tag({"name": "Completionist"})

    # Create performer in local stash with Completionist tag
    local_stash_instance.create_performer({
        **performer.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Run the plugin
    job_id = local_stash_instance.run_plugin_task("CompleteTheStash", "Complete The Stash!")
    local_stash_instance.wait_for_job(job_id, timeout=600)

    # Verify performer was created in missing stash
    missing_performer = missing_stash_instance.find_performer(performer.name)
    assert missing_performer is not None
    assert missing_performer["name"] == performer.name
    assert missing_performer["gender"] == performer.gender

    # Verify non-compilation scenes were created in missing stash
    verify_scene_exists(missing_stash_instance, quality_work)
    verify_scene_exists(missing_stash_instance, gimme_all)

    # Verify compilation scene was NOT created
    verify_scene_not_exists(missing_stash_instance, teamwork_vol_2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
