import os
import urllib.request

import pytest
from stashapi import log

from test_helpers import (
    STASHBOX_INTERNAL_PORT,
    PerformerBuilder,
    SceneBuilder,
    StashBoxClient,
    find_or_create_tag,
    verify_scene_exists,
    verify_scene_not_exists,
)

from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashCompleter import StashCompleter
from StashDbClient import StashDbClient


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


def test_smoke_in_container(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Smoke test: verify plugin runs when installed in container.

    This is a simple in-container test to verify the plugin can be installed
    and executed in Stash. The same functionality is tested more thoroughly
    by direct execution tests with better coverage/debugging.
    """
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )

    # Use internal endpoint for stash_ids (what containers see)
    internal_endpoint = f"http://stashbox:{STASHBOX_INTERNAL_PORT}/graphql"

    # Build minimal test data
    performer = PerformerBuilder("Smoke Test Performer", "FEMALE")
    studio_id = stashbox.create_studio("Smoke Test Studio")

    stashbox.create_performer(performer)
    performer.stash_endpoint = internal_endpoint

    scene = (SceneBuilder("Smoke Test Scene", "2024-01-15")
             .with_performers(performer.stashbox_id)
             .with_studio(studio_id))

    stashbox.create_scene(scene)
    scene.stash_endpoint = internal_endpoint

    # Create performer in local stash
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        **performer.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Run the plugin via container
    job_id = local_stash_instance.run_plugin_task("CompleteTheStash", "Complete The Stash!")
    local_stash_instance.wait_for_job(job_id, timeout=600)

    # Basic verification - just check scene was created
    verify_scene_exists(missing_stash_instance, scene)


def test_basic_workflow(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test basic workflow: performer with scenes are created in missing stash."""
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )
    external_endpoint = stashbox_instance["endpoint"]

    # Build test data
    performer = PerformerBuilder("Jade Summers", "FEMALE")
    studio_id = stashbox.create_studio("Basic Workflow Studio")

    stashbox.create_performer(performer)
    performer.stash_endpoint = external_endpoint

    scene1 = (SceneBuilder("Morning Session", "2024-01-15")
              .with_performers(performer.stashbox_id)
              .with_studio(studio_id))
    scene2 = (SceneBuilder("Evening Delight", "2024-02-20")
              .with_performers(performer.stashbox_id)
              .with_studio(studio_id))

    stashbox.create_scene(scene1)
    stashbox.create_scene(scene2)
    scene1.stash_endpoint = external_endpoint
    scene2.stash_endpoint = external_endpoint

    # Create performer in local stash
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        **performer.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Run plugin directly
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)
    completer.process_performers()

    # Verify results
    missing_performer = missing_stash_instance.find_performer(performer.name)
    assert missing_performer is not None
    assert missing_performer["name"] == performer.name
    assert missing_performer["gender"] == performer.gender

    verify_scene_exists(missing_stash_instance, scene1)
    verify_scene_exists(missing_stash_instance, scene2)


def test_compilation_exclusion(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test that scenes tagged with 'Compilation' are excluded."""
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )
    external_endpoint = stashbox_instance["endpoint"]

    # Build test data
    compilation_tag_id = stashbox.create_tag("Compilation")
    performer = PerformerBuilder("Ruby Valentine", "FEMALE")
    studio_id = stashbox.create_studio("Compilation Test Studio")

    stashbox.create_performer(performer)
    performer.stash_endpoint = external_endpoint

    regular_scene = (SceneBuilder("Regular Scene", "2024-01-15")
                     .with_performers(performer.stashbox_id)
                     .with_studio(studio_id))
    compilation_scene = (SceneBuilder("Best Of Collection", "2024-02-20")
                         .with_performers(performer.stashbox_id)
                         .with_studio(studio_id)
                         .with_tags(compilation_tag_id))

    stashbox.create_scene(regular_scene)
    stashbox.create_scene(compilation_scene)
    regular_scene.stash_endpoint = external_endpoint
    compilation_scene.stash_endpoint = external_endpoint

    # Create performer in local stash
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        **performer.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Run plugin directly
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)
    completer.process_performers()

    # Verify regular scene was created
    verify_scene_exists(missing_stash_instance, regular_scene)

    # Verify compilation scene was NOT created
    verify_scene_not_exists(missing_stash_instance, compilation_scene)


def test_idempotency(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test that running plugin twice does not create duplicate scenes.

    On the second run, the existing performer should be updated (not re-created)
    and the existing studio should be reused (not re-created).
    """
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )
    external_endpoint = stashbox_instance["endpoint"]

    # Build test data
    performer = PerformerBuilder("Aria Stone", "FEMALE")
    studio_id = stashbox.create_studio("Idempotency Studio")

    stashbox.create_performer(performer)
    performer.stash_endpoint = external_endpoint

    scene1 = (SceneBuilder("First Run Scene A", "2024-03-01")
              .with_performers(performer.stashbox_id)
              .with_studio(studio_id))
    scene2 = (SceneBuilder("First Run Scene B", "2024-03-02")
              .with_performers(performer.stashbox_id)
              .with_studio(studio_id))

    stashbox.create_scene(scene1)
    stashbox.create_scene(scene2)
    scene1.stash_endpoint = external_endpoint
    scene2.stash_endpoint = external_endpoint

    # Create performer in local stash
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        **performer.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Build clients
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)

    # First run - scenes should be created
    completer.process_performers()
    verify_scene_exists(missing_stash_instance, scene1)
    verify_scene_exists(missing_stash_instance, scene2)

    # Second run - no duplicates should be created
    completer.process_performers()
    verify_scene_exists(missing_stash_instance, scene1)
    verify_scene_exists(missing_stash_instance, scene2)


def test_destroy_scene_when_added_to_local(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test that scenes are destroyed from missing stash when added to local stash."""
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )
    external_endpoint = stashbox_instance["endpoint"]

    # Build test data - performer with 2 scenes
    performer = PerformerBuilder("Mia Rivers", "FEMALE")
    studio_id = stashbox.create_studio("Destroy Test Studio")

    stashbox.create_performer(performer)
    performer.stash_endpoint = external_endpoint

    scene_to_keep = (SceneBuilder("Scene To Keep", "2024-01-15")
                     .with_performers(performer.stashbox_id)
                     .with_studio(studio_id))
    scene_to_destroy = (SceneBuilder("Scene To Destroy", "2024-02-20")
                        .with_performers(performer.stashbox_id)
                        .with_studio(studio_id))

    stashbox.create_scene(scene_to_keep)
    stashbox.create_scene(scene_to_destroy)
    scene_to_keep.stash_endpoint = external_endpoint
    scene_to_destroy.stash_endpoint = external_endpoint

    # Create performer in local stash
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        **performer.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Build clients
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)

    # First run - both scenes should be created in missing stash
    completer.process_performers()
    verify_scene_exists(missing_stash_instance, scene_to_keep)
    verify_scene_exists(missing_stash_instance, scene_to_destroy)

    # Add one scene to local stash (simulating user has acquired it)
    local_stash_instance.create_scene(scene_to_destroy.for_stash_create())

    # Second run - scene_to_destroy should be destroyed from missing stash
    completer.process_performers()

    # Verify scene_to_keep still exists in missing stash
    verify_scene_exists(missing_stash_instance, scene_to_keep)

    # Verify scene_to_destroy was destroyed from missing stash
    verify_scene_not_exists(missing_stash_instance, scene_to_destroy)


def test_process_scene_by_id(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test the hook pathway - process_scene_by_id destroys scene from missing stash."""
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )
    external_endpoint = stashbox_instance["endpoint"]

    # Build test data
    performer = PerformerBuilder("Nina Brooks", "FEMALE")
    studio_id = stashbox.create_studio("Hook Test Studio")

    stashbox.create_performer(performer)
    performer.stash_endpoint = external_endpoint

    scene = (SceneBuilder("Hook Test Scene", "2024-03-15")
             .with_performers(performer.stashbox_id)
             .with_studio(studio_id))

    stashbox.create_scene(scene)
    scene.stash_endpoint = external_endpoint

    # Create performer in local stash
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        **performer.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Build clients
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)

    # First run - scene created in missing stash
    completer.process_performers()
    verify_scene_exists(missing_stash_instance, scene)

    # Create the same scene in local stash (simulating scene.Create hook trigger)
    local_scene = local_stash_instance.create_scene(scene.for_stash_create())

    # Call process_scene_by_id (the hook pathway)
    completer.process_scene_by_id(local_scene["id"])

    # Verify scene was destroyed from missing stash
    verify_scene_not_exists(missing_stash_instance, scene)


def test_process_scene_by_id_not_found(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test error early returns in process_scene_by_id."""
    external_endpoint = stashbox_instance["endpoint"]

    # Build clients
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)

    # Test 1: Call with non-existent scene ID - should not raise error
    completer.process_scene_by_id(99999)

    # Test 2: Create scene WITHOUT stash_ids and call process_scene_by_id
    scene_without_stash_id = local_stash_instance.create_scene({"title": "No Stash ID Scene"})
    completer.process_scene_by_id(scene_without_stash_id["id"])

    # If we get here without exception, the test passes


def test_parent_studio_creation(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test that parent-child studio relationship is created correctly."""
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )
    external_endpoint = stashbox_instance["endpoint"]

    # Build test data with parent-child studio relationship
    performer = PerformerBuilder("Stella Moon", "FEMALE")
    parent_studio_id = stashbox.create_studio("Network Studios")
    child_studio_id = stashbox.create_studio("Sub Channel", parent_id=parent_studio_id)

    stashbox.create_performer(performer)
    performer.stash_endpoint = external_endpoint

    scene = (SceneBuilder("Parent Studio Test", "2024-04-01")
             .with_performers(performer.stashbox_id)
             .with_studio(child_studio_id))

    stashbox.create_scene(scene)
    scene.stash_endpoint = external_endpoint

    # Create performer in local stash
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        **performer.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Build clients
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)
    completer.process_performers()

    # Verify scene was created
    verify_scene_exists(missing_stash_instance, scene)

    # Verify child studio was created with correct parent
    # Need to specify fragment to include parent_studio
    child_studios = missing_stash_instance.find_studios(
        {"name": {"value": "Sub Channel", "modifier": "EQUALS"}},
        fragment="id name parent_studio { id name }",
    )
    assert len(child_studios) == 1
    child_studio = child_studios[0]
    assert child_studio["parent_studio"] is not None
    assert child_studio["parent_studio"]["name"] == "Network Studios"

    # Verify parent studio was also created
    parent_studios = missing_stash_instance.find_studios(
        {"name": {"value": "Network Studios", "modifier": "EQUALS"}},
    )
    assert len(parent_studios) == 1


def test_multi_performer_scene(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test scene with multiple performers where only one is tracked."""
    stashbox = StashBoxClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"]
    )
    external_endpoint = stashbox_instance["endpoint"]

    # Build test data - 2 performers, but only 1 in local stash
    performer_tracked = PerformerBuilder("Tracked Performer", "FEMALE")
    performer_not_tracked = PerformerBuilder("Not Tracked Performer", "FEMALE")
    studio_id = stashbox.create_studio("Multi Performer Studio")

    stashbox.create_performer(performer_tracked)
    stashbox.create_performer(performer_not_tracked)
    performer_tracked.stash_endpoint = external_endpoint
    performer_not_tracked.stash_endpoint = external_endpoint

    # Scene with both performers
    scene = (SceneBuilder("Multi Performer Scene", "2024-05-01")
             .with_performers(performer_tracked.stashbox_id, performer_not_tracked.stashbox_id)
             .with_studio(studio_id))

    stashbox.create_scene(scene)
    scene.stash_endpoint = external_endpoint

    # Create ONLY the tracked performer in local stash with Completionist tag
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        **performer_tracked.for_stash_create(),
        "tag_ids": [completionist_tag["id"]],
    })

    # Build clients
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)
    completer.process_performers()

    # Verify scene was created
    verify_scene_exists(missing_stash_instance, scene)

    # Query scene with explicit fragment to verify performer count
    scenes = missing_stash_instance.find_scenes(
        {
            "stash_id_endpoint": {
                "endpoint": scene.stash_endpoint,
                "stash_id": scene.stashbox_id,
                "modifier": "EQUALS",
            }
        },
        fragment="id title performers { id name }",
    )
    assert len(scenes) == 1
    created_scene = scenes[0]

    # Verify only the tracked performer is attached to the scene
    assert len(created_scene["performers"]) == 1
    assert created_scene["performers"][0]["name"] == performer_tracked.name


def test_performer_without_stash_id(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
):
    """Test that performers without stash_ids are skipped with a warning."""
    external_endpoint = stashbox_instance["endpoint"]

    # Create performer in local stash WITHOUT stash_ids
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        "name": "No Stash ID Performer",
        "gender": "FEMALE",
        "tag_ids": [completionist_tag["id"]],
        # No stash_ids!
    })

    # Build clients
    os.environ["STASHDB_ENDPOINT"] = external_endpoint

    local_client = LocalStashClient(
        {
            "Scheme": local_stash_instance._test_scheme,
            "Host": local_stash_instance._test_host,
            "Port": local_stash_instance._test_port,
            "ApiKey": local_stash_instance._test_api_key,
        },
        log,
    )

    missing_client = MissingStashClient(
        missing_stash_instance._test_scheme,
        missing_stash_instance._test_host,
        missing_stash_instance._test_port,
        missing_stash_instance._test_api_key,
        external_endpoint,
        log,
    )

    stashbox_client = StashDbClient(
        stashbox_instance["endpoint"],
        stashbox_instance["api_key"],
    )

    config = {
        "performerTags": ["Completionist"],
        "stashboxEndpoint": external_endpoint,
        "sceneExcludeTags": ["Compilation"],
        "enableSceneHooks": False,
    }

    completer = StashCompleter(config, log, stashbox_client, local_client, missing_client)

    # Should not raise an error
    completer.process_performers()

    # Verify performer was NOT created in missing stash
    missing_performers = missing_stash_instance.find_performers({
        "name": {"value": "No Stash ID Performer", "modifier": "EQUALS"}
    })
    assert len(missing_performers) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
