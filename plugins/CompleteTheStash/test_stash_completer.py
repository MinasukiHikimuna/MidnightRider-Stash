import unittest
from unittest.mock import MagicMock
from datetime import datetime

from StashCompleter import StashCompleter
from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashDbClient import StashDbClient


class TestStashCompleter(unittest.TestCase):

    def setUp(self):
        self.config = MagicMock()
        self.logger = MagicMock()
        self.stashdb_client = MagicMock(spec=StashDbClient)
        self.local_stash_client = MagicMock(spec=LocalStashClient)
        self.missing_stash_client = MagicMock(spec=MissingStashClient)

        self.stash_completer = StashCompleter(
            self.config,
            self.logger,
            self.stashdb_client,
            self.local_stash_client,
            self.missing_stash_client,
        )

    def test_compare_scenes(self):
        local_scenes = [
            {"stash_ids": [{"stash_id": "1", "endpoint": "http://example.com"}]}
        ]
        existing_missing_scenes = [
            {"stash_ids": [{"stash_id": "2", "endpoint": "http://example.com"}]}
        ]
        stashdb_scenes = [{"id": "3"}, {"id": "1"}]

        self.config.STASHDB_ENDPOINT = "http://example.com"

        new_missing_scenes = self.stash_completer.compare_scenes(
            local_scenes, existing_missing_scenes, stashdb_scenes
        )

        self.assertEqual(len(new_missing_scenes), 1)
        self.assertEqual(new_missing_scenes[0]["id"], "3")

    def test_create_scene(self):
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

        self.config.STASHDB_ENDPOINT = "http://example.com"
        self.missing_stash_client.get_or_create_tag.side_effect = [{"id": 1}, {"id": 2}]
        self.missing_stash_client.create_scene.return_value = {"id": "1"}

        scene_id = self.stash_completer.create_scene(scene, performer_ids, studio_id)

        self.assertEqual(scene_id, "1")
        self.missing_stash_client.create_scene.assert_called_once()

    def test_get_or_create_studio_by_stash_id(self):
        studio = {"id": "1", "name": "Test Studio"}
        parent_studio_id = None

        self.config.STASHDB_ENDPOINT = "http://example.com"
        self.missing_stash_client.find_studios.return_value = []

        self.stashdb_client.query_studio_image.return_value = (
            "http://example.com/image.jpg"
        )
        self.missing_stash_client.create_studio.return_value = {"id": "1"}

        studio_id = self.stash_completer.get_or_create_studio_by_stash_id(
            studio, parent_studio_id
        )

        self.assertEqual(studio_id, "1")
        self.missing_stash_client.create_studio.assert_called_once()

    def test_get_or_create_missing_performer(self):
        performer_name = "Test Performer"
        performer_stash_id = "1"

        self.config.STASHDB_ENDPOINT = "http://example.com"
        self.missing_stash_client.find_performers_by_stash_id.return_value = []
        self.stashdb_client.query_performer_image.return_value = (
            "http://example.com/image.jpg"
        )
        self.missing_stash_client.create_performer.return_value = {"id": "1"}

        performer_id = self.stash_completer.get_or_create_missing_performer(
            performer_name, performer_stash_id
        )

        self.assertEqual(performer_id, "1")
        self.missing_stash_client.create_performer.assert_called_once()

    def test_find_selected_local_performers(self):
        self.config.PERFORMER_TAGS = ["tag1", "tag2"]
        self.local_stash_client.find_tag.side_effect = [{"id": 1}, {"id": 2}]
        self.local_stash_client.find_performers.return_value = [
            {"id": 1, "name": "Performer1"}
        ]

        performers = self.stash_completer.find_selected_local_performers()

        self.assertEqual(len(performers), 1)
        self.assertEqual(performers[0]["id"], 1)

    def test_process_performers(self):
        self.config.STASHDB_ENDPOINT = "http://example.com"

        selected_performers = [
            {
                "id": 1,
                "name": "Performer1",
                "stash_ids": [{"stash_id": "1", "endpoint": "http://example.com"}],
            }
        ]
        self.stash_completer.find_selected_local_performers = MagicMock(
            return_value=selected_performers
        )
        self.stash_completer.get_or_create_missing_performer = MagicMock(return_value=1)
        self.stash_completer.process_performer = MagicMock()

        self.stash_completer.process_performers()

        self.stash_completer.find_selected_local_performers.assert_called_once()
        self.stash_completer.get_or_create_missing_performer.assert_called_once_with(
            "Performer1", "1"
        )
        self.stash_completer.process_performer.assert_called_once_with(1, {"1": 1})

    def test_process_performer(self):
        self.config.STASHDB_ENDPOINT = "http://example.com"

        local_performer_id = 1
        missing_performers_by_stash_id = {"1": 1}
        local_performer_details = {
            "name": "Performer1",
            "stash_ids": [{"stash_id": "1", "endpoint": "http://example.com"}],
            "scenes": [],
        }
        self.local_stash_client.find_performer.return_value = local_performer_details
        self.missing_stash_client.find_performer.return_value = {"scenes": []}
        self.stashdb_client.query_scenes.return_value = []

        self.stash_completer.process_performer(
            local_performer_id, missing_performers_by_stash_id
        )

        self.local_stash_client.find_performer.assert_called_once_with(
            local_performer_id
        )
        self.missing_stash_client.find_performer.assert_called_once_with(1)
        self.stashdb_client.query_scenes.assert_called_once_with("1")

    def test_process_updated_scene(self):
        stash_id = "1"
        self.missing_stash_client.find_scenes_by_stash_id.return_value = [
            {"id": "1", "title": "Scene1"}
        ]

        self.stash_completer.process_updated_scene(stash_id)

        self.missing_stash_client.find_scenes_by_stash_id.assert_called_once_with(
            stash_id
        )
        self.missing_stash_client.destroy_scene.assert_called_once_with("1")


if __name__ == "__main__":
    unittest.main()
