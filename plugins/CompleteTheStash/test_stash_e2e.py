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
    os.getenv("STASH_API_KEY") is not None
), "STASH_API_KEY environment variable is not set"


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
            "version": "0.3.1-bfefac7",
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
def local_stash_instance():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(test_dir, ".template-stash")
    local_working_dir = os.path.join(test_dir, ".local-stash")
    plugin_dir = os.path.join(local_working_dir, "plugins", "CompleteTheStash")
    executable_path = os.getenv("STASH_BIN")
    local_config_path = os.path.join(template_dir, "local-config.yml")
    local_apikey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ0ZXN0Iiwic3ViIjoiQVBJS2V5IiwiaWF0IjoxNzIxODgwNjM0fQ.8CDVgMWaCdKjfO1_o0fgjxj3mCUpj-FkiI-ePAvuDgc"

    if os.path.exists(local_working_dir):
        shutil.rmtree(local_working_dir)
    os.makedirs(local_working_dir, exist_ok=True)

    with open(local_config_path, "r") as file:
        local_config = yaml.safe_load(file)
    local_config["apikey"] = local_apikey
    local_config["stash_boxes"][0]["apikey"] = os.getenv("STASH_API_KEY")
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
            "ApiKey": local_apikey,
        }
    )

    stop_stash_process(stash_process)


@pytest.fixture(scope="module")
def missing_stash_instance():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(test_dir, ".template-stash")
    missing_working_dir = os.path.join(test_dir, ".missing-stash")
    executable_path = os.getenv("STASH_BIN")
    missing_config_path = os.path.join(template_dir, "missing-config.yml")
    missing_apikey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJ0ZXN0Iiwic3ViIjoiQVBJS2V5IiwiaWF0IjoxNzIxODgwNjUxfQ.TiTtehm66znchYYm0za7szdKlfKFi97CHsXO_vcgP38"

    if os.path.exists(missing_working_dir):
        shutil.rmtree(missing_working_dir)
    os.makedirs(missing_working_dir, exist_ok=True)

    with open(missing_config_path, "r") as file:
        missing_config = yaml.safe_load(file)
    missing_config["apikey"] = missing_apikey
    missing_config["stash_boxes"][0]["apikey"] = os.getenv("STASH_API_KEY")
    with open(os.path.join(missing_working_dir, "config.yml"), "w") as file:
        yaml.safe_dump(missing_config, file)

    stash_process = start_stash_process(executable_path, missing_working_dir)

    yield StashInterface(
        {
            "scheme": "http",
            "host": "localhost",
            "port": 6662,
            "apikey": missing_apikey,
            "logger": log,
        }
    )

    stop_stash_process(stash_process)


def test_complete_the_stash(
    local_stash_instance: StashInterface, missing_stash_instance: StashInterface
):
    tag = local_stash_instance.create_tag({"name": "Completionist"})

    performer_kelly = (
        PerformerBuilder()
        .with_name("Kelly Collins")
        .with_stash_id(
            "bfbf1de8-0208-4282-a3cd-7abe2d0588c0", "https://stashdb.org/graphql"
        )
        .build()
    )
    performer_alissa = (
        PerformerBuilder()
        .with_name("Alissa Noir")
        .with_stash_id(
            "a68a7630-4282-4d60-9734-6f695dea6ab8", "https://stashdb.org/graphql"
        )
        .build()
    )

    scene_quality_work = (
        SceneBuilder()
        .with_title("Quality Work")
        .with_stash_id(
            "102f92cd-24c2-4832-94ad-f7dacaab087c", "https://stashdb.org/graphql"
        )
        .build()
    )
    scene_stuns_in_bed = (
        SceneBuilder()
        .with_title("Stuns In Bed")
        .with_stash_id(
            "fe95429c-5ee1-4bd3-ae7d-5612746421a9", "https://stashdb.org/graphql"
        )
        .build()
    )
    scene_gimme_all = (
        SceneBuilder()
        .with_title("Gimme All")
        .with_stash_id(
            "53a49432-672e-4105-9c43-8bb0fe0e3807", "https://stashdb.org/graphql"
        )
        .build()
    )

    performer_kelly_local = local_stash_instance.create_performer(
        {**performer_kelly, "tag_ids": [tag["id"]]}
    )
    performer_alissa_local = local_stash_instance.create_performer(
        {**performer_alissa, "tag_ids": [tag["id"]]}
    )

    job_id = local_stash_instance.run_plugin_task(
        "CompleteTheStash", "Process performers"
    )
    local_stash_instance.wait_for_job(job_id)

    performer_kelly_missing = missing_stash_instance.find_performer(
        performer_kelly.get("name")
    )
    assert performer_kelly_missing is not None
    assert performer_kelly_missing.get("name") == "Kelly Collins"
    assert performer_kelly_missing.get("stash_ids") == [
        {
            "endpoint": "https://stashdb.org/graphql",
            "stash_id": performer_kelly.get("stash_ids")[0].get("stash_id"),
        }
    ]
    assert performer_kelly_missing.get("scene_count") > 0
    assert len(performer_kelly_missing.get("scenes")) > 0

    missing_quality_work = missing_stash_instance.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": "https://stashdb.org/graphql",
                "stash_id": scene_quality_work.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_quality_work) == 1
    assert missing_quality_work[0].get("title") == scene_quality_work.get("title")
    assert missing_quality_work[0].get("stash_ids") == [
        {
            "endpoint": "https://stashdb.org/graphql",
            "stash_id": scene_quality_work.get("stash_ids")[0].get("stash_id"),
        }
    ]
    assert_scene_performers(missing_quality_work[0], [performer_kelly_missing])

    missing_gimme_all = missing_stash_instance.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": "https://stashdb.org/graphql",
                "stash_id": scene_gimme_all.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_gimme_all) == 1
    assert missing_gimme_all[0].get("title") == scene_gimme_all.get("title")
    assert missing_gimme_all[0].get("stash_ids") == [
        {
            "endpoint": "https://stashdb.org/graphql",
            "stash_id": scene_gimme_all.get("stash_ids")[0].get("stash_id"),
        }
    ]
    assert_scene_performers(missing_gimme_all[0], [performer_kelly_missing])

    missing_stuns_in_bed = missing_stash_instance.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": "https://stashdb.org/graphql",
                "stash_id": scene_stuns_in_bed.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_stuns_in_bed) == 1
    assert missing_stuns_in_bed[0].get("title") == scene_stuns_in_bed.get("title")
    assert missing_stuns_in_bed[0].get("stash_ids") == [
        {
            "endpoint": "https://stashdb.org/graphql",
            "stash_id": scene_stuns_in_bed.get("stash_ids")[0].get("stash_id"),
        }
    ]
    assert_scene_performers(
        missing_stuns_in_bed[0], [performer_kelly_local, performer_alissa_local]
    )

    # Test: Scene is created with stash_id
    local_stash_instance.create_scene(
        {
            "title": scene_gimme_all.get("title"),
            "stash_ids": [
                {
                    "stash_id": scene_gimme_all.get("stash_ids")[0].get("stash_id"),
                    "endpoint": "https://stashdb.org/graphql",
                }
            ],
        }
    )
    missing_gimme_all = missing_stash_instance.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": "https://stashdb.org/graphql",
                "stash_id": scene_gimme_all.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_gimme_all) == 0

    # Test: Scene is updated with stash_id
    local_quality_work = local_stash_instance.create_scene(
        {"title": scene_quality_work.get("title")}
    )
    local_stash_instance.update_scene(
        {
            "id": local_quality_work["id"],
            "title": scene_quality_work.get("title"),
            "stash_ids": [
                {
                    "stash_id": scene_quality_work.get("stash_ids")[0].get("stash_id"),
                    "endpoint": "https://stashdb.org/graphql",
                }
            ],
        }
    )

    missing_quality_work = missing_stash_instance.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": "https://stashdb.org/graphql",
                "stash_id": scene_quality_work.get("stash_ids")[0].get("stash_id"),
                "modifier": "EQUALS",
            }
        }
    )
    assert len(missing_quality_work) == 0


def assert_scene_performers(scene, expected_performers):
    assert set([performer.get("id") for performer in scene.get("performers")]) == set(
        [expected_performer.get("id") for expected_performer in expected_performers]
    )


if __name__ == "__main__":
    pytest.main([__file__])
