import base64
import mimetypes

import requests
from stashapi.stashapp import StashInterface

from constants import DEFAULT_IMAGE_FORMAT
from graphql_queries import PERFORMER_FRAGMENT, SCENE_FRAGMENT


class LocalStashClient:
    def __init__(self, server_connection: dict, logger):
        self.server_connection = server_connection
        self.local_stash = StashInterface(server_connection)
        self.logger = logger

    @staticmethod
    def create_with_server_connect(server_connection: dict, logger):
        return LocalStashClient(server_connection, logger)

    @staticmethod
    def create_with_api_key(scheme: str, host: str, port: int, api_key: str, logger):
        return LocalStashClient(
            {
                "scheme": scheme,
                "host": host,
                "port": port,
                "apikey": api_key,
            },
            logger,
        )

    def get_configuration(self):
        return self.local_stash.get_configuration()

    def find_tag(self, tag_name):
        return self.local_stash.find_tag({"name": tag_name})

    def find_performers(self, performer_filter, filter):
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

    def find_scene_by_id(self, scene_id):
        return self.local_stash.find_scene(scene_id)

    def find_performer(self, performer_id: int) -> dict:
        create = False
        return self.local_stash.find_performer(performer_id, create, PERFORMER_FRAGMENT)

    def find_all_scenes(self):
        return self.local_stash.find_scenes(fragment=SCENE_FRAGMENT)

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
