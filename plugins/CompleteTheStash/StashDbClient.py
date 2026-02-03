import requests
import stashapi.log as logger

from constants import SCENES_PER_PAGE
from StashboxClient import StashboxClient


class StashDbClient(StashboxClient):
    def __init__(self, endpoint, api_key):
        self.endpoint = endpoint
        self.api_key = api_key

    def query_performer_image(self, performer_stash_id):
        query = """
            query FindPerformer($id: ID!) {
                findPerformer(id: $id) {
                    id
                    images {
                        id
                        url
                    }
                }
            }
        """
        result = self._gql_query(query, {"id": performer_stash_id})
        if result:
            performer_data = result["data"]["findPerformer"]
            if (
                performer_data
                and performer_data["images"]
                and len(performer_data["images"]) > 0
            ):
                return performer_data["images"][0]["url"]
            logger.error(
                f"No image found for performer with Stash ID {performer_stash_id}."
            )
            return None

        logger.error(f"Failed to query performer with Stash ID {performer_stash_id}.")
        return None

    def query_studio_image(self, studio_stash_id):
        query = """
            query FindStudio($id: ID!) {
                findStudio(id: $id) {
                    id
                    images {
                        id
                        url
                    }
                }
            }
        """
        result = self._gql_query(query, {"id": studio_stash_id})
        if result:
            studio_data = result["data"]["findStudio"]
            if (
                studio_data
                and studio_data["images"]
                and len(studio_data["images"]) > 0
            ):
                return studio_data["images"][0]["url"]
            logger.error(
                f"No image found for studio with Stash ID {studio_stash_id}."
            )
            return None

        logger.error(f"Failed to query studio with Stash ID {studio_stash_id}.")
        return None

    def query_scenes(self, performer_stash_id):
        query = f"""
            query QueryScenes($stash_ids: [ID!]!, $page: Int!) {{
                queryScenes(
                    input: {{
                        performers: {{
                            value: $stash_ids,
                            modifier: INCLUDES
                        }},
                        per_page: 25,
                        page: $page
                    }}
                ) {{
                    scenes {{ {self._SCENE_FRAGMENT} }}
                    count
                }}
            }}
        """
        return self._paginate_scenes(query, {"stash_ids": performer_stash_id})

    _SCENE_FRAGMENT = """
        id
        title
        details
        release_date
        urls {
            url
            site {
                name
                url
            }
        }
        studio {
            id
            name
            parent {
                id
                name
            }
        }
        images {
            id
            url
        }
        performers {
            performer {
                id
                name
                disambiguation
                gender
                aliases
                birth_date
                breast_type
                cup_size
                ethnicity
                country
                hair_color
                eye_color
                images {
                    id
                    url
                }
            }
        }
        duration
        code
        tags {
            id
            name
        }
    """

    def query_scenes_by_studio(self, studio_stash_ids: list[str]):
        query = f"""
            query QueryScenes($studio_ids: [ID!]!, $page: Int!) {{
                queryScenes(
                    input: {{
                        studios: {{
                            value: $studio_ids,
                            modifier: INCLUDES
                        }},
                        per_page: 25,
                        page: $page
                    }}
                ) {{
                    scenes {{ {self._SCENE_FRAGMENT} }}
                    count
                }}
            }}
        """
        return self._paginate_scenes(query, {"studio_ids": studio_stash_ids})

    def query_scenes_by_tag(self, tag_id: str, tag_name: str | None = None):
        query = f"""
            query QueryScenes($tag_ids: [ID!]!, $page: Int!) {{
                queryScenes(
                    input: {{
                        tags: {{
                            value: $tag_ids,
                            modifier: INCLUDES
                        }},
                        per_page: 25,
                        page: $page
                    }}
                ) {{
                    scenes {{ {self._SCENE_FRAGMENT} }}
                    count
                }}
            }}
        """
        return self._paginate_scenes(query, {"tag_ids": [tag_id]})

    def find_studio_children(self, studio_stash_id: str) -> list[dict]:
        query = """
            query FindStudio($id: ID!) {
                findStudio(id: $id) {
                    child_studios {
                        id
                        name
                    }
                }
            }
        """
        result = self._gql_query(query, {"id": studio_stash_id})
        if result:
            studio_data = result["data"]["findStudio"]
            if studio_data:
                return studio_data.get("child_studios", [])
        logger.error(f"Failed to find studio children for Stash ID {studio_stash_id}.")
        return []

    def find_tag_id(self, tag_name: str) -> str | None:
        query = """
            query QueryTags($name: String!) {
                queryTags(input: { name: $name, per_page: 25 }) {
                    tags {
                        id
                        name
                    }
                }
            }
        """
        result = self._gql_query(query, {"name": tag_name})
        if result:
            tags = result["data"]["queryTags"]["tags"]
            for tag in tags:
                if tag["name"].lower() == tag_name.lower():
                    return tag["id"]
        logger.warning(f"Tag '{tag_name}' not found on StashDB.")
        return None

    def _paginate_scenes(self, query, variables):
        scenes = []
        page = 1
        total_scenes = None
        while True:
            result = self._gql_query(query, {**variables, "page": page})
            if result:
                scenes_data = result["data"]["queryScenes"]
                scenes.extend(scenes_data["scenes"])
                total_scenes = total_scenes or scenes_data["count"]
                if len(scenes) >= total_scenes or len(scenes_data["scenes"]) < SCENES_PER_PAGE:
                    break
                page += 1
            else:
                break
        return scenes

    def _gql_query(self, query, variables=None):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Apikey"] = self.api_key
        response = requests.post(
            self.endpoint,
            json={"query": query, "variables": variables},
            headers=headers,
        )
        if response.status_code == 200:
            return response.json()
        logger.error(
            f"Query failed with status code {response.status_code}: {response.text}"
        )
        return None
