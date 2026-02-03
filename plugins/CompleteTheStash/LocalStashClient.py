import base64
import mimetypes
from typing import Any

import requests
from stashapi.stashapp import StashInterface

from constants import DEFAULT_IMAGE_FORMAT
from graphql_queries import PERFORMER_FRAGMENT, SCENE_FRAGMENT
from stash_types import Performer, Scene, ServerConnection, Tag


class LocalStashClient:
    def __init__(self, server_connection: ServerConnection, logger: Any) -> None:
        self.server_connection = server_connection
        self.local_stash = StashInterface(server_connection)
        self.logger = logger

    @staticmethod
    def create_with_server_connect(server_connection: ServerConnection, logger: Any) -> "LocalStashClient":
        return LocalStashClient(server_connection, logger)

    @staticmethod
    def create_with_api_key(scheme: str, host: str, port: int, api_key: str, logger: Any) -> "LocalStashClient":
        return LocalStashClient(
            {
                "scheme": scheme,
                "host": host,
                "port": port,
                "apikey": api_key,
            },
            logger,
        )

    def get_configuration(self) -> dict[str, Any]:
        return self.local_stash.get_configuration()

    def find_tag(self, tag_name: str) -> Tag | None:
        return self.local_stash.find_tag({"name": tag_name})

    def find_performers(self, performer_filter: dict[str, Any], filter: dict[str, Any]) -> list[Performer]:
        performers = self.local_stash.find_performers(performer_filter, filter)
        # Download performer images using session cookie
        if performers:
            session = requests.Session()
            cookie = self.server_connection.get("SessionCookie", {})
            session.cookies.set(
                cookie.get("Name"),
                cookie.get("Value"),
                domain=cookie.get("Domain"),
                path=cookie.get("Path"),
                secure=cookie.get("Secure"),
            )

            for performer in performers:
                if "image_path" in performer:
                    image_url = performer["image_path"]
                    try:
                        response = session.get(image_url)
                        response.raise_for_status()

                        content_type = response.headers.get("Content-Type", "")
                        image_type = mimetypes.guess_extension(content_type)

                        image_type = image_type.lstrip(".") if image_type else DEFAULT_IMAGE_FORMAT

                        image_data = base64.b64encode(response.content).decode("utf-8")
                        data_url = f"data:image/{image_type};base64,{image_data}"
                        performer["image"] = data_url
                        self.logger.debug(f"Downloaded image for performer {performer['name']}")
                    except requests.RequestException as e:
                        self.logger.error(f"Failed to download image for performer {performer['name']}: {e!s}")
        return performers

    def find_scene_by_id(self, scene_id: int) -> Scene | None:
        return self.local_stash.find_scene(scene_id)

    def find_performer(self, performer_id: int) -> Performer | None:
        create = False
        return self.local_stash.find_performer(performer_id, create, PERFORMER_FRAGMENT)

    def find_all_scenes(self) -> list[Scene]:
        return self.local_stash.find_scenes(fragment=SCENE_FRAGMENT)

    def find_scenes_paginated(self, page: int, per_page: int) -> list[Scene]:
        """Find scenes with pagination support."""
        filter = {"page": page, "per_page": per_page}
        return self.local_stash.find_scenes(filter=filter, fragment=SCENE_FRAGMENT)

    def find_studios_by_tags(self, tag_ids: list[str]):
        studios = []
        page = 1
        while True:
            result = self.local_stash.find_studios(
                {
                    "tags": {"value": tag_ids, "modifier": "INCLUDES"},
                },
                {
                    "page": page,
                    "per_page": 25,
                },
                fragment="id name stash_ids { stash_id endpoint }",
            )
            studios.extend(result)
            if len(result) < 25:
                break
            page += 1
        return studios

    def find_child_tags(self, parent_tag_id: str):
        return self.local_stash.find_tags(
            {
                "parents": {"value": [parent_tag_id], "modifier": "INCLUDES", "depth": 0},
            },
            fragment="id name",
        )
