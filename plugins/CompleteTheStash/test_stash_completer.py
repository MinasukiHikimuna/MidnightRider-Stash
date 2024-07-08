import pytest
from unittest.mock import MagicMock
from datetime import datetime
from StashCompleter import StashCompleter
from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashDbClient import StashDbClient


@pytest.fixture
def stash_completer():
    config = MagicMock()
    logger = MagicMock()
    stashdb_client = MagicMock(spec=StashDbClient)
    local_stash_client = MagicMock(spec=LocalStashClient)
    missing_stash_client = MagicMock(spec=MissingStashClient)

    return StashCompleter(
        config,
        logger,
        stashdb_client,
        local_stash_client,
        missing_stash_client,
    )


def test_compare_scenes(stash_completer):
    local_scenes = [
        {
            "stash_ids": [
                {
                    "stash_id": "11111111-1111-1111-1111-111111111111",
                    "endpoint": "http://example.com",
                }
            ]
        }
    ]
    existing_missing_scenes = [
        {
            "stash_ids": [
                {
                    "stash_id": "22222222-2222-2222-2222-222222222222",
                    "endpoint": "http://example.com",
                }
            ]
        }
    ]
    stashdb_scenes = [
        {"id": "11111111-1111-1111-1111-111111111111"},
        {"id": "22222222-2222-2222-2222-222222222222"},
        {"id": "33333333-3333-3333-3333-333333333333"},
    ]

    stash_completer.config.STASHDB_ENDPOINT = "http://example.com"

    new_missing_scenes = stash_completer.compare_scenes(
        local_scenes, existing_missing_scenes, stashdb_scenes
    )

    assert len(new_missing_scenes) == 1
    assert new_missing_scenes[0]["id"] == "33333333-3333-3333-3333-333333333333"


def test_create_scene(stash_completer):
    scene = {
        "code": "123",
        "title": "Test Scene",
        "urls": [{"url": "http://example.com"}],
        "release_date": "2022-01-01",
        "images": [{"url": "http://example.com/image.jpg"}],
        "id": "1",
        "tags": [{"name": "tag1"}, {"name": "tag2"}],
        "details": "Test details",
    }
    performer_ids = [1, 2]
    studio_id = 1

    stash_completer.config.STASHDB_ENDPOINT = "http://example.com"
    stash_completer.missing_stash_client.get_or_create_tag.side_effect = [
        {"id": 1},
        {"id": 2},
    ]
    stash_completer.missing_stash_client.create_scene.return_value = {"id": "1"}

    scene_id = stash_completer.create_scene(scene, performer_ids, studio_id)

    assert scene_id == "1"
    stash_completer.missing_stash_client.create_scene.assert_called_once()


def test_get_or_create_studio_by_stash_id(stash_completer):
    studio = {"id": "1", "name": "Test Studio"}
    parent_studio_id = None

    stash_completer.config.STASHDB_ENDPOINT = "http://example.com"
    stash_completer.missing_stash_client.find_studios.return_value = []

    stash_completer.stashdb_client.query_studio_image.return_value = (
        "http://example.com/image.jpg"
    )
    stash_completer.missing_stash_client.create_studio.return_value = {"id": "1"}

    studio_id = stash_completer.get_or_create_studio_by_stash_id(
        studio, parent_studio_id
    )

    assert studio_id == "1"
    stash_completer.missing_stash_client.create_studio.assert_called_once()


def test_get_or_create_missing_performer(stash_completer):
    performer_name = "Test Performer"
    performer_stash_id = "1"

    stash_completer.config.STASHDB_ENDPOINT = "http://example.com"
    stash_completer.missing_stash_client.find_performers_by_stash_id.return_value = []
    stash_completer.stashdb_client.query_performer_image.return_value = (
        "http://example.com/image.jpg"
    )
    stash_completer.missing_stash_client.create_performer.return_value = {"id": "1"}

    performer_id = stash_completer.get_or_create_missing_performer(
        performer_name, performer_stash_id
    )

    assert performer_id == "1"
    stash_completer.missing_stash_client.create_performer.assert_called_once()


def test_find_selected_local_performers(stash_completer):
    stash_completer.config.PERFORMER_TAGS = ["tag1", "tag2"]
    stash_completer.local_stash_client.find_tag.side_effect = [{"id": 1}, {"id": 2}]
    stash_completer.local_stash_client.find_performers.return_value = [
        {"id": 1, "name": "Performer1"}
    ]

    performers = stash_completer.find_selected_local_performers()

    assert len(performers) == 1
    assert performers[0]["id"] == 1


def test_process_performers(stash_completer):
    stash_completer.config.STASHDB_ENDPOINT = "http://example.com"

    selected_performers = [
        {
            "id": 1,
            "name": "Performer1",
            "stash_ids": [{"stash_id": "1", "endpoint": "http://example.com"}],
        }
    ]
    stash_completer.find_selected_local_performers = MagicMock(
        return_value=selected_performers
    )
    stash_completer.get_or_create_missing_performer = MagicMock(return_value=1)
    stash_completer.process_performer = MagicMock()

    stash_completer.process_performers()

    stash_completer.find_selected_local_performers.assert_called_once()
    stash_completer.get_or_create_missing_performer.assert_called_once_with(
        "Performer1", "1"
    )
    stash_completer.process_performer.assert_called_once_with(1, {"1": 1})


def test_process_performer(stash_completer):
    stash_completer.config.STASHDB_ENDPOINT = "http://example.com"

    local_performer_id = 1
    missing_performers_by_stash_id = {"1": 1}
    local_performer_details = {
        "name": "Performer1",
        "stash_ids": [{"stash_id": "1", "endpoint": "http://example.com"}],
        "scenes": [],
    }
    stash_completer.local_stash_client.find_performer.return_value = (
        local_performer_details
    )
    stash_completer.missing_stash_client.find_performer.return_value = {"scenes": []}
    stash_completer.stashdb_client.query_scenes.return_value = []

    stash_completer.process_performer(
        local_performer_id, missing_performers_by_stash_id
    )

    stash_completer.local_stash_client.find_performer.assert_called_once_with(
        local_performer_id
    )
    stash_completer.missing_stash_client.find_performer.assert_called_once_with(1)
    stash_completer.stashdb_client.query_scenes.assert_called_once_with("1")


def test_process_updated_scene(stash_completer):
    stash_id = "1"
    stash_completer.missing_stash_client.find_scenes_by_stash_id.return_value = [
        {"id": "1", "title": "Scene1"}
    ]

    stash_completer.process_updated_scene(stash_id)

    stash_completer.missing_stash_client.find_scenes_by_stash_id.assert_called_once_with(
        stash_id
    )
    stash_completer.missing_stash_client.destroy_scene.assert_called_once_with("1")
