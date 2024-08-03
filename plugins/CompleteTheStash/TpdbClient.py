import json
import requests
import stashapi.log as logger

from StashboxClient import StashboxClient


class TpdbClient(StashboxClient):
    def __init__(self, endpoint, api_key):
        self.endpoint = endpoint
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def query_performer_image(self, performer_stash_id):
        response = requests.get(
            f"https://api.theporndb.net/performers/{performer_stash_id}",
            headers=self.headers,
        )
        if response.status_code == 200:
            performer_data = response.json()
            if performer_data.get("data"):
                return performer_data["data"]["image"]
            else:
                logger.error(
                    f"No image found for performer with Stash ID {performer_stash_id}."
                )
        else:
            logger.error(
                f"Query failed with status code {response.status_code}: {response.text}"
            )

        return None

    def query_studio_image(self, studio_stash_id):
        response = requests.get(
            f"https://api.theporndb.net/sites/{studio_stash_id}",
            headers=self.headers,
        )
        if response.status_code == 200:
            studio_data = response.json()
            if studio_data.get("data"):
                return studio_data["data"]["logo"]
            else:
                logger.error(
                    f"No image found for studio with Stash ID {studio_stash_id}."
                )
        else:
            logger.error(
                f"Query failed with status code {response.status_code}: {response.text}"
            )

        return None

    def query_scenes(self, performer_stash_id):
        performer_response = requests.get(
            f"https://api.theporndb.net/performers/{performer_stash_id}",
            headers=self.headers,
        )

        if performer_response.status_code == 200:
            performer_data = performer_response.json()
            if performer_data.get("data"):
                performer_internal_id = performer_data["data"]["_id"]
                performer_name = performer_data["data"]["name"]
            else:
                logger.error(
                    f"No performer found for performer with Stash ID {performer_stash_id}."
                )
                return None
        else:
            logger.error(
                f"Query failed with status code {performer_response.status_code}: {performer_response.text}"
            )
            return None

        scenes = []
        page = 1
        while True:
            url = f"https://api.theporndb.net/scenes?performers[{performer_internal_id}]={performer_name}&page={page}&per_page=25"
            logger.debug(f"Querying scenes for performer {performer_name} from {url}")
            response = requests.get(
                url,
                headers=self.headers,
            )
            if response.status_code == 200:
                scenes_data = response.json()
                for scene_data in scenes_data.get("data", []):
                    studio = {
                        "id": scene_data.get("site", {}).get("uuid"),
                        "name": scene_data.get("site", {}).get("name"),
                    }
                    if scene_data.get("site", {}).get("network"):
                        studio["parent"] = {
                            "id": scene_data.get("site", {})
                            .get("network", {})
                            .get("uuid"),
                            "name": scene_data.get("site", {})
                            .get("network", {})
                            .get("name"),
                        }

                    performers = [
                        {
                            "performer": {
                                "id": scene_data_performer.get("parent").get("id"),
                                "name": scene_data_performer.get("parent").get("name"),
                            }
                        }
                        for scene_data_performer in scene_data.get("performers", [])
                        if scene_data_performer.get("parent") is not None
                    ]

                    scene = {
                        "id": scene_data.get("id"),
                        "title": scene_data.get("title"),
                        "details": scene_data.get("description"),
                        "release_date": scene_data.get("date"),
                        "urls": [
                            {
                                "url": scene_data.get("url"),
                                "site": {"name": "Studio", "url": ""},
                            }
                        ],
                        "studio": studio,
                        "images": [
                            {
                                "url": scene_data.get("background", {}).get("full"),
                            }
                        ],
                        "performers": performers,
                        "duration": scene_data.get("duration"),
                        "code": scene_data.get("external_id"),
                        "tags": scene_data.get("tags"),
                    }
                    scenes.append(scene)

                if scenes_data.get("meta", {}).get("last_page") == page:
                    break

                page += 1
            else:
                logger.error(
                    f"Query failed with status code {response.status_code}: {response.text}"
                )
                return None

        logger.debug(f"Found {len(scenes)} scenes for performer {performer_name}.")

        return scenes
