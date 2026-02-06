"""Workflow tests for CompleteTheStash plugin."""

import pytest

from test_helpers import (
    PerformerBuilder,
    SceneBuilder,
    StashBoxClient,
    find_or_create_tag,
    verify_scene_exists,
    verify_scene_not_exists,
)


def test_basic_workflow(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
    make_completer,
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

    # Run plugin
    completer = make_completer()
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
    make_completer,
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

    # Run plugin
    completer = make_completer()
    completer.process_performers()

    # Verify regular scene was created
    verify_scene_exists(missing_stash_instance, regular_scene)

    # Verify compilation scene was NOT created
    verify_scene_not_exists(missing_stash_instance, compilation_scene)


def test_idempotency(
    stashbox_instance,
    local_stash_instance,
    missing_stash_instance,
    make_completer,
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

    # Run plugin
    completer = make_completer()

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
    make_completer,
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

    # Run plugin
    completer = make_completer()

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
    make_completer,
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

    # Run plugin
    completer = make_completer()

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
    make_completer,
):
    """Test error early returns in process_scene_by_id."""
    completer = make_completer()

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
    make_completer,
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

    # Run plugin
    completer = make_completer()
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
    make_completer,
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

    # Run plugin
    completer = make_completer()
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
    make_completer,
):
    """Test that performers without stash_ids are skipped with a warning."""
    # Create performer in local stash WITHOUT stash_ids
    completionist_tag = find_or_create_tag(local_stash_instance, "Completionist")
    local_stash_instance.create_performer({
        "name": "No Stash ID Performer",
        "gender": "FEMALE",
        "tag_ids": [completionist_tag["id"]],
        # No stash_ids!
    })

    # Run plugin
    completer = make_completer()

    # Should not raise an error
    completer.process_performers()

    # Verify performer was NOT created in missing stash
    missing_performers = missing_stash_instance.find_performers({
        "name": {"value": "No Stash ID Performer", "modifier": "EQUALS"}
    })
    assert len(missing_performers) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
