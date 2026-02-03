from typing import Any

from stashapi.stashapp import StashInterface

from graphql_queries import PERFORMER_FRAGMENT, SCENE_FRAGMENT
from stash_types import Performer, Scene, Studio, Tag


class MissingStashClient:
    def __init__(self, scheme: str, host: str, port: int, api_key: str, stash_db_endpoint: str, logger: Any) -> None:
        self.stash_db_endpoint = stash_db_endpoint
        self.missing_stash = StashInterface(
            {
                "scheme": scheme,
                "host": host,
                "port": port,
                "apikey": api_key,
                "logger": logger,
            }
        )
        self.logger = logger

    def get_configuration(self) -> dict[str, Any]:
        return self.missing_stash.get_configuration()

    def get_or_create_tag(self, tag_name: str) -> Tag:
        # Use create=False first to avoid stashapi's info-level logging on creation
        tag = self.missing_stash.find_tag({"name": tag_name}, create=False)
        if tag:
            return tag
        self.logger.debug(f"Could not find tag with name='{tag_name}', creating")
        return self.missing_stash.create_tag({"name": tag_name})

    def create_scene(self, scene_data: dict[str, Any]) -> Scene | None:
        return self.missing_stash.create_scene(scene_data)

    def destroy_scene(self, scene_id: int) -> None:
        scene = self.missing_stash.find_scene(scene_id, fragment="id")
        if scene:
            self.missing_stash.destroy_scene(scene_id)

    def find_performer(self, performer_id: int) -> Performer | None:
        create = False
        return self.missing_stash.find_performer(performer_id, create, PERFORMER_FRAGMENT)

    def find_studios(self, studio_filter: dict[str, Any]) -> list[Studio]:
        return self.missing_stash.find_studios(studio_filter)

    def create_studio(self, studio_data: dict[str, Any]) -> Studio | None:
        return self.missing_stash.create_studio(studio_data)

    def create_performer(self, performer_data: dict[str, Any]) -> Performer | None:
        return self.missing_stash.create_performer(performer_data)

    def update_performer(self, performer_data: dict[str, Any]) -> Performer | None:
        return self.missing_stash.update_performer(performer_data)

    def find_scenes_by_stash_id(self, stash_id: str) -> list[Scene]:
        return self.missing_stash.find_scenes(
            {
                "stash_id_endpoint": {
                    "stash_id": stash_id,
                    "endpoint": self.stash_db_endpoint,
                    "modifier": "EQUALS",
                }
            }
        )

    def find_performers_by_stash_id(self, stash_id: str) -> list[Performer]:
        return self.missing_stash.find_performers(
            {
                "stash_id_endpoint": {
                    "stash_id": stash_id,
                    "endpoint": self.stash_db_endpoint,
                    "modifier": "EQUALS",
                }
            }
        )

    def find_all_scenes(self) -> list[Scene]:
        return self.missing_stash.find_scenes(fragment=SCENE_FRAGMENT)
