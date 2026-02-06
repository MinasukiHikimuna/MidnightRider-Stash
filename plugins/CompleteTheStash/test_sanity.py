"""Sanity tests for stashbox connectivity and basic operations."""

import urllib.request

import pytest

from test_helpers import (
    STASHBOX_INTERNAL_PORT,
    PerformerBuilder,
    SceneBuilder,
    StashBoxClient,
    find_or_create_tag,
    verify_scene_exists,
)


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
