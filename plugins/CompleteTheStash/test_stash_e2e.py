import os
import shutil
import subprocess
from datetime import datetime

import pytest
import yaml
from dotenv import load_dotenv

import stashapi.log as log
from stashapi.stashapp import StashInterface

load_dotenv()

assert os.getenv("STASH_BIN") is not None, "STASH_BIN environment variable is not set"
assert (
    os.getenv("STASHDB_API_KEY") is not None
), "STASHDB_API_KEY environment variable is not set"
assert (
    os.getenv("TPDB_API_KEY") is not None
), "TPDB_API_KEY environment variable is not set"


local_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ0ZXN0Iiwic3ViIjoiQVBJS2V5IiwiaWF0IjoxNzIxODgwNjM0fQ.8CDVgMWaCdKjfO1_o0fgjxj3mCUpj-FkiI-ePAvuDgc"
missing_stashdb_port = 6662
missing_stashdb_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ0ZXN0Iiwic3ViIjoiQVBJS2V5IiwiaWF0IjoxNzIxODgwNjUxfQ.TiTtehm66znchYYm0za7szdKlfKFi97CHsXO_vcgP38"
missing_tpdb_port = 6663
missing_tpdb_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ0ZXN0Iiwic3ViIjoiQVBJS2V5IiwiaWF0IjoxNzIyMzM2ODcyfQ.ta4AsOkuJ6tVoZoMVJmxioZgluGo6oiNks-crAqDj8E"


def start_stash_process(executable_path, working_dir) -> subprocess.Popen[bytes]:
    return subprocess.Popen([executable_path, "--nobrowser"], cwd=working_dir)


def stop_stash_process(stash_process):
    stash_process.terminate()
    stash_process.wait()


def copy_files_to_plugin_directory(source_dir, target_dir, excluded_files):
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    files_copied = []

    for filename in os.listdir(source_dir):
        if filename not in excluded_files and not filename.startswith("test_"):
            source_file = os.path.join(source_dir, filename)
            if os.path.isfile(source_file):
                shutil.copy(source_file, target_dir)
                files_copied.append(filename)

    return files_copied


def create_manifest_file(target_dir, files_copied):
    manifest_content = {
        "id": "CompleteTheStash",
        "name": "CompleteTheStash",
        "metadata": {
            "description": "Finds missing scenes for selected performers and creates missing scene metadata to another missing Stash instance.",
            "version": "0.0.0-abcdefg",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "requires": [],
            "source_repository": "https://minasukihikimuna.github.io/MidnightRider-Stash/index.yml",
        },
        "files": files_copied,
    }

    with open(os.path.join(target_dir, "manifest.yml"), "w") as file:
        yaml.safe_dump(manifest_content, file)


class PerformerBuilder:
    def __init__(self):
        self.performer = {"name": "", "stash_ids": []}

    def with_name(self, name):
        self.performer["name"] = name
        return self

    def with_stash_id(self, stash_id, endpoint):
        self.performer["stash_ids"].append({"stash_id": stash_id, "endpoint": endpoint})
        return self

    def build(self):
        return self.performer


class SceneBuilder:
    def __init__(self):
        self.scene = {"title": "", "stash_ids": []}

    def with_title(self, title):
        self.scene["title"] = title
        return self

    def with_stash_id(self, stash_id, endpoint):
        self.scene["stash_ids"].append({"stash_id": stash_id, "endpoint": endpoint})
        return self

    def build(self):
        return self.scene


@pytest.fixture(scope="module")
def local_stash_instance_stashdb():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(test_dir, ".template-stash")
    local_working_dir = os.path.join(test_dir, ".local-stash")
    plugin_dir = os.path.join(local_working_dir, "plugins", "CompleteTheStash")
    executable_path = os.getenv("STASH_BIN")
    local_config_path = os.path.join(template_dir, "local-config.txt")

    if os.path.exists(local_working_dir):
        shutil.rmtree(local_working_dir)
    os.makedirs(local_working_dir, exist_ok=True)

    with open(local_config_path, "r") as file:
        local_config = yaml.safe_load(file)
    local_config["api_key"] = local_api_key

    stashdb_found = False
    for stash_box in local_config.get("stash_boxes", []):
        if stash_box.get("endpoint") == "https://stashdb.org/graphql":
            stash_box["apikey"] = os.getenv("STASHDB_API_KEY")
            stashdb_found = True
            break
    assert stashdb_found, "StashDB endpoint not found in local-config.txt"

    local_config["plugins"]["settings"]["CompleteTheStash"][
        "performerTags"
    ] = "Completionist"
    local_config["plugins"]["settings"]["CompleteTheStash"][
        "sceneExcludeTags"
    ] = "Compilation"
    local_config["plugins"]["settings"]["CompleteTheStash"][
        "missingStashAddress"
    ] = f"http://localhost:{missing_stashdb_port}"
    local_config["plugins"]["settings"]["CompleteTheStash"][
        "missingStashApiKey"
    ] = missing_stashdb_api_key

    with open(os.path.join(local_working_dir, "config.yml"), "w") as file:
        yaml.safe_dump(local_config, file)

    excluded_files = {".gitignore"}
    files_copied = copy_files_to_plugin_directory(test_dir, plugin_dir, excluded_files)
    create_manifest_file(plugin_dir, files_copied)

    stash_process = start_stash_process(executable_path, local_working_dir)

    yield StashInterface(
        {
            "scheme": "http",
            "host": "localhost",
            "port": 6661,
            "logger": log,
            "ApiKey": local_api_key,
        }
    )

    stop_stash_process(stash_process)


@pytest.fixture(scope="module")
def local_stash_instance_tpdb():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(test_dir, ".template-stash")
    local_working_dir = os.path.join(test_dir, ".local-stash")
    plugin_dir = os.path.join(local_working_dir, "plugins", "CompleteTheStash")
    executable_path = os.getenv("STASH_BIN")
    local_config_path = os.path.join(template_dir, "local-config.txt")

    if os.path.exists(local_working_dir):
        shutil.rmtree(local_working_dir)
    os.makedirs(local_working_dir, exist_ok=True)

    with open(local_config_path, "r") as file:
        local_config = yaml.safe_load(file)
    local_config["api_key"] = local_api_key

    tpdb_found = False
    for stash_box in local_config.get("stash_boxes", []):
        if stash_box.get("endpoint") == "https://theporndb.net/graphql":
            stash_box["apikey"] = os.getenv("TPDB_API_KEY")
            tpdb_found = True
            break
    assert tpdb_found, "TPDB endpoint not found in local-config.txt"

    local_config["plugins"]["settings"]["CompleteTheStash"][
        "performerTags"
    ] = "Completionist"
    local_config["plugins"]["settings"]["CompleteTheStash"][
        "sceneExcludeTags"
    ] = "Compilation"
    local_config["plugins"]["settings"]["CompleteTheStash"][
        "missingStashTpdbAddress"
    ] = f"http://localhost:{missing_tpdb_port}"
    local_config["plugins"]["settings"]["CompleteTheStash"][
        "missingStashTpdbApiKey"
    ] = missing_tpdb_api_key

    with open(os.path.join(local_working_dir, "config.yml"), "w") as file:
        yaml.safe_dump(local_config, file)

    excluded_files = {".gitignore"}
    files_copied = copy_files_to_plugin_directory(test_dir, plugin_dir, excluded_files)
    create_manifest_file(plugin_dir, files_copied)

    stash_process = start_stash_process(executable_path, local_working_dir)

    yield StashInterface(
        {
            "scheme": "http",
            "host": "localhost",
            "port": 6661,
            "logger": log,
            "ApiKey": local_api_key,
        }
    )

    stop_stash_process(stash_process)


@pytest.fixture(scope="module")
def missing_stash_instance_stashdb():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(test_dir, ".template-stash")
    missing_working_dir = os.path.join(test_dir, ".missing-stashdb-stash")
    executable_path = os.getenv("STASH_BIN")
    missing_config_path = os.path.join(template_dir, "missing-stashdb-config.txt")

    if os.path.exists(missing_working_dir):
        shutil.rmtree(missing_working_dir)
    os.makedirs(missing_working_dir, exist_ok=True)

    with open(missing_config_path, "r") as file:
        missing_config = yaml.safe_load(file)
    missing_config["api_key"] = missing_stashdb_api_key
    missing_config["stash_boxes"][0]["apikey"] = os.getenv("STASHDB_API_KEY")
    with open(os.path.join(missing_working_dir, "config.yml"), "w") as file:
        yaml.safe_dump(missing_config, file)

    stash_process = start_stash_process(executable_path, missing_working_dir)

    yield StashInterface(
        {
            "scheme": "http",
            "host": "localhost",
            "port": missing_stashdb_port,
            "apikey": missing_stashdb_api_key,
            "logger": log,
        }
    )

    stop_stash_process(stash_process)


@pytest.fixture(scope="module")
def missing_stash_instance_tpdb():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(test_dir, ".template-stash")
    missing_working_dir = os.path.join(test_dir, ".missing-tpdb-stash")
    executable_path = os.getenv("STASH_BIN")
    missing_config_path = os.path.join(template_dir, "missing-tpdb-config.txt")

    if os.path.exists(missing_working_dir):
        shutil.rmtree(missing_working_dir)
    os.makedirs(missing_working_dir, exist_ok=True)

    with open(missing_config_path, "r") as file:
        missing_config = yaml.safe_load(file)
    missing_config["api_key"] = missing_tpdb_api_key
    missing_config["stash_boxes"][0]["apikey"] = os.getenv("TPDB_API_KEY")
    with open(os.path.join(missing_working_dir, "config.yml"), "w") as file:
        yaml.safe_dump(missing_config, file)

    stash_process = start_stash_process(executable_path, missing_working_dir)

    yield StashInterface(
        {
            "scheme": "http",
            "host": "localhost",
            "port": missing_tpdb_port,
            "apikey": missing_tpdb_api_key,
            "logger": log,
        }
    )

    stop_stash_process(stash_process)


def test_stashdb(
    local_stash_instance_stashdb: StashInterface,
    missing_stash_instance_stashdb: StashInterface,
):
    graphql_endpoint = "https://stashdb.org/graphql"
    tag = local_stash_instance_stashdb.create_tag({"name": "Completionist"})

    performer_kelly = (
        PerformerBuilder()
        .with_name("Kelly Collins")
        .with_stash_id("bfbf1de8-0208-4282-a3cd-7abe2d0588c0", graphql_endpoint)
        .build()
    )
    performer_alissa = (
        PerformerBuilder()
        .with_name("Alissa Foxy")
        .with_stash_id("a68a7630-4282-4d60-9734-6f695dea6ab8", graphql_endpoint)
        .build()
    )
    performer_alexis = (PerformerBuilder()
        .with_name("Alexis Crystal")
        .with_stash_id("f1f1e7a-5380-4c4f-92b1-c340f48f8c94", "https://anotherendpoint.com/graphql")
        .build()
    )

    scene_quality_work = (
        SceneBuilder()
        .with_title("Quality Work")
        .with_stash_id("102f92cd-24c2-4832-94ad-f7dacaab087c", graphql_endpoint)
        .build()
    )
    scene_stuns_in_bed = (
        SceneBuilder()
        .with_title("Stuns In Bed")
        .with_stash_id("fe95429c-5ee1-4bd3-ae7d-5612746421a9", graphql_endpoint)
        .build()
    )
    scene_gimme_all = (
        SceneBuilder()
        .with_title("Gimme All")
        .with_stash_id("53a49432-672e-4105-9c43-8bb0fe0e3807", graphql_endpoint)
        .build()
    )
    scene_teamwork_vol_2 = (
        SceneBuilder()
        .with_title("Teamwork Vol 2")
        .with_stash_id("e7f63585-4393-453d-8c82-9104ba04dffe", graphql_endpoint)
        .build()
    )

    performer_kelly_local = local_stash_instance_stashdb.create_performer(
        {**performer_kelly, "tag_ids": [tag["id"]]}
    )
    performer_alissa_local = local_stash_instance_stashdb.create_performer(
        {**performer_alissa, "tag_ids": [tag["id"]]}
    )
    performer_alexis_local = local_stash_instance_stashdb.create_performer(
        {**performer_alexis, "tag_ids": [tag["id"]]}
    )

    job_id = local_stash_instance_stashdb.run_plugin_task(
        "CompleteTheStash", "Complete The Stash!"
    )
    local_stash_instance_stashdb.wait_for_job(job_id, timeout=600)

    performer_kelly_missing = missing_stash_instance_stashdb.find_performer(
        performer_kelly.get("name")
    )
    assert performer_kelly_missing is not None
    assert performer_kelly_missing.get("name") == "Kelly Collins"
    assert performer_kelly_missing.get("stash_ids") == [
        {
            "endpoint": graphql_endpoint,
            "stash_id": performer_kelly.get("stash_ids")[0].get("stash_id"),
        }
    ]
    assert performer_kelly_missing.get("scene_count") > 0
    assert len(performer_kelly_missing.get("scenes")) > 0

    missing_quality_work = find_scene_by_stash_id(
        missing_stash_instance_stashdb,
        scene_quality_work.get("stash_ids")[0].get("stash_id"),
        graphql_endpoint,
    )
    assert_scene(missing_quality_work, scene_quality_work)
    assert_scene_performers(missing_quality_work[0], [performer_kelly_missing])

    missing_gimme_all = find_scene_by_stash_id(
        missing_stash_instance_stashdb,
        scene_gimme_all.get("stash_ids")[0].get("stash_id"),
        graphql_endpoint,
    )
    assert_scene(missing_gimme_all, scene_gimme_all)
    assert_scene_performers(missing_gimme_all[0], [performer_kelly_missing])

    missing_stuns_in_bed = find_scene_by_stash_id(
        missing_stash_instance_stashdb,
        scene_stuns_in_bed.get("stash_ids")[0].get("stash_id"),
        graphql_endpoint,
    )
    assert_scene(missing_stuns_in_bed, scene_stuns_in_bed)
    assert_scene_performers(
        missing_stuns_in_bed[0], [performer_kelly_local, performer_alissa_local]
    )

    assert_scene_does_not_exist(
        missing_stash_instance_stashdb,
        scene_teamwork_vol_2.get("stash_ids")[0].get("stash_id"),
        graphql_endpoint,
    )

    # Test: Scene is created with stash_id
    local_stash_instance_stashdb.create_scene(
        {
            "title": scene_gimme_all.get("title"),
            "stash_ids": [
                {
                    "stash_id": scene_gimme_all.get("stash_ids")[0].get("stash_id"),
                    "endpoint": graphql_endpoint,
                }
            ],
        }
    )
    missing_gimme_all = missing_stash_instance_stashdb.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": graphql_endpoint,
                "stash_id": scene_gimme_all.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_gimme_all) == 0

    # Test: Scene is updated with stash_id
    local_quality_work = local_stash_instance_stashdb.create_scene(
        {"title": scene_quality_work.get("title")}
    )
    local_stash_instance_stashdb.update_scene(
        {
            "id": local_quality_work["id"],
            "title": scene_quality_work.get("title"),
            "stash_ids": [
                {
                    "stash_id": scene_quality_work.get("stash_ids")[0].get("stash_id"),
                    "endpoint": graphql_endpoint,
                }
            ],
        }
    )

    missing_quality_work = missing_stash_instance_stashdb.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": graphql_endpoint,
                "stash_id": scene_quality_work.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_quality_work) == 0


def test_tpdb(
    local_stash_instance_tpdb: StashInterface,
    missing_stash_instance_tpdb: StashInterface,
):
    graphql_endpoint = "https://theporndb.net/graphql"
    tag = local_stash_instance_tpdb.create_tag({"name": "Completionist"})

    performer_kelly = (
        PerformerBuilder()
        .with_name("Kelly Collins")
        .with_stash_id("e1321ecc-1214-4389-bd2e-5b5db1ee8407", graphql_endpoint)
        .build()
    )
    performer_alissa = (
        PerformerBuilder()
        .with_name("Alissa Foxy")
        .with_stash_id("19dcb2e9-1bfb-40b1-9567-ed8670bb4efc", graphql_endpoint)
        .build()
    )
    performer_alexis = (PerformerBuilder()
        .with_name("Alexis Crystal")
        .with_stash_id("f1f1e7a-5380-4c4f-92b1-c340f48f8c94", "https://anotherendpoint.com/graphql")
        .build()
    )

    scene_quality_work = (
        SceneBuilder()
        .with_title("Quality Work")
        .with_stash_id("bfe652a9-63ae-4c39-8acd-b8ebb7f94b07", graphql_endpoint)
        .build()
    )
    scene_stuns_in_bed = (
        SceneBuilder()
        .with_title("Stuns In Bed")
        .with_stash_id("c9af78ea-1192-4ff8-b144-b64e77d9aba3", graphql_endpoint)
        .build()
    )
    scene_gimme_all = (
        SceneBuilder()
        .with_title("Gimme All")
        .with_stash_id("c2500ae1-7abf-4d32-9d98-faaec881a383", graphql_endpoint)
        .build()
    )
    scene_teamwork_vol_2 = (
        SceneBuilder()
        .with_title("Teamwork Vol 2")
        .with_stash_id("f1fe9e7a-5380-4c4f-92b1-c340f48f8c94", graphql_endpoint)
        .build()
    )

    performer_kelly_local = local_stash_instance_tpdb.create_performer(
        {**performer_kelly, "tag_ids": [tag["id"]]}
    )
    performer_alissa_local = local_stash_instance_tpdb.create_performer(
        {**performer_alissa, "tag_ids": [tag["id"]]}
    )
    performer_alexis_local = local_stash_instance_tpdb.create_performer(
        {**performer_alexis, "tag_ids": [tag["id"]]}
    )

    job_id = local_stash_instance_tpdb.run_plugin_task(
        "CompleteTheStash", "Complete The Stash!"
    )
    local_stash_instance_tpdb.wait_for_job(job_id, timeout=600)

    performer_kelly_missing = missing_stash_instance_tpdb.find_performer(
        performer_kelly.get("name")
    )
    assert performer_kelly_missing is not None
    assert performer_kelly_missing.get("name") == "Kelly Collins"
    assert performer_kelly_missing.get("stash_ids") == [
        {
            "endpoint": graphql_endpoint,
            "stash_id": performer_kelly.get("stash_ids")[0].get("stash_id"),
        }
    ]
    assert performer_kelly_missing.get("scene_count") > 0
    assert len(performer_kelly_missing.get("scenes")) > 0

    missing_quality_work = find_scene_by_stash_id(
        missing_stash_instance_tpdb,
        scene_quality_work.get("stash_ids")[0].get("stash_id"),
        graphql_endpoint,
    )
    assert_scene(missing_quality_work, scene_quality_work)
    assert_scene_performers(missing_quality_work[0], [performer_kelly_missing])

    missing_gimme_all = find_scene_by_stash_id(
        missing_stash_instance_tpdb,
        scene_gimme_all.get("stash_ids")[0].get("stash_id"),
        graphql_endpoint,
    )
    assert_scene(missing_gimme_all, scene_gimme_all)
    assert_scene_performers(missing_gimme_all[0], [performer_kelly_missing])

    missing_stuns_in_bed = find_scene_by_stash_id(
        missing_stash_instance_tpdb,
        scene_stuns_in_bed.get("stash_ids")[0].get("stash_id"),
        graphql_endpoint,
    )
    assert_scene(missing_stuns_in_bed, scene_stuns_in_bed)
    assert_scene_performers(
        missing_stuns_in_bed[0], [performer_kelly_local, performer_alissa_local]
    )

    assert_scene_does_not_exist(
        missing_stash_instance_tpdb,
        scene_teamwork_vol_2.get("stash_ids")[0].get("stash_id"),
        graphql_endpoint,
    )

    # Test: Scene is created with stash_id
    local_stash_instance_tpdb.create_scene(
        {
            "title": scene_gimme_all.get("title"),
            "stash_ids": [
                {
                    "stash_id": scene_gimme_all.get("stash_ids")[0].get("stash_id"),
                    "endpoint": graphql_endpoint,
                }
            ],
        }
    )
    missing_gimme_all = missing_stash_instance_tpdb.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": graphql_endpoint,
                "stash_id": scene_gimme_all.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_gimme_all) == 0

    # Test: Scene is updated with stash_id
    local_quality_work = local_stash_instance_tpdb.create_scene(
        {"title": scene_quality_work.get("title")}
    )
    local_stash_instance_tpdb.update_scene(
        {
            "id": local_quality_work["id"],
            "title": scene_quality_work.get("title"),
            "stash_ids": [
                {
                    "stash_id": scene_quality_work.get("stash_ids")[0].get("stash_id"),
                    "endpoint": graphql_endpoint,
                }
            ],
        }
    )

    missing_quality_work = missing_stash_instance_tpdb.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": graphql_endpoint,
                "stash_id": scene_quality_work.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_quality_work) == 0


def find_scene_by_stash_id(stash_instance, stash_id, endpoint):
    return stash_instance.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": endpoint,
                "stash_id": stash_id,
                "modifier": "EQUALS",
            }
        }
    )


def assert_scene(matched_scenes, expected_scene):
    assert len(matched_scenes) == 1

    matched_scene = matched_scenes[0]
    assert matched_scene.get("title").upper() == expected_scene.get("title").upper()
    assert set(
        [stash_id.get("stash_id") for stash_id in matched_scene.get("stash_ids")]
    ) == set([stash_id.get("stash_id") for stash_id in expected_scene.get("stash_ids")])


def assert_scene_does_not_exist(stash_instance, stash_id, endpoint):
    matched_scenes = stash_instance.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": endpoint,
                "stash_id": stash_id,
                "modifier": "EQUALS",
            }
        }
    )
    assert len(matched_scenes) == 0


def assert_scene_performers(scene, expected_performers):
    assert set([performer.get("id") for performer in scene.get("performers")]) == set(
        [expected_performer.get("id") for expected_performer in expected_performers]
    )


if __name__ == "__main__":
    pytest.main([__file__])
