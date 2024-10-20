import requests
import stashapi.log as logger

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
            else:
                logger.error(
                    f"No image found for performer with Stash ID {performer_stash_id}."
                )
                return None

        logger.error(f"Failed to query performer with Stash ID {performer_stash_id}.")
        return None

    def query_studio_image(self, performer_stash_id):
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
        result = self._gql_query(query, {"id": performer_stash_id})
        if result:
            performer_data = result["data"]["findStudio"]
            if (
                performer_data
                and performer_data["images"]
                and len(performer_data["images"]) > 0
            ):
                return performer_data["images"][0]["url"]
            else:
                logger.error(
                    f"No image found for studio with Stash ID {performer_stash_id}."
                )
                return None

        logger.error(f"Failed to query studio with Stash ID {performer_stash_id}.")
        return None

    def query_scenes(self, performer_stash_id):
        query = """
            query QueryScenes($stash_ids: [ID!]!, $page: Int!) {
                queryScenes(
                    input: {
                        performers: {
                            value: $stash_ids,
                            modifier: INCLUDES
                        },
                        per_page: 25,
                        page: $page
                    }
                ) {
                    scenes {
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
                    }
                    count
                }
            }
        """
        scenes = []
        page = 1
        total_scenes = None
        while True:
            result = self._gql_query(
                query, {"stash_ids": performer_stash_id, "page": page}
            )
            if result:
                scenes_data = result["data"]["queryScenes"]
                scenes.extend(scenes_data["scenes"])
                total_scenes = total_scenes or scenes_data["count"]
                if len(scenes) >= total_scenes or len(scenes_data["scenes"]) < 25:
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
        else:
            logger.error(
                f"Query failed with status code {response.status_code}: {response.text}"
            )
            return None
