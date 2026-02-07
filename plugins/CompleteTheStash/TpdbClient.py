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

        url = f"https://api.theporndb.net/scenes?performers[{performer_internal_id}]={performer_name}"
        scenes = self._paginate_scenes(url)
        if scenes is not None:
            logger.debug(f"Found {len(scenes)} scenes for performer {performer_name}.")
        return scenes

    def query_scenes_by_studio(self, studio_stash_ids: list[str]):
        all_scenes = []
        for studio_id in studio_stash_ids:
            scenes = self._paginate_scenes(
                f"https://api.theporndb.net/sites/{studio_id}/scenes"
            )
            if scenes is not None:
                all_scenes.extend(scenes)
        return all_scenes

    def query_scenes_by_tag(self, tag_id: str, tag_name: str | None = None):
        return self._paginate_scenes(
            f"https://api.theporndb.net/scenes?tags[{tag_id}]={tag_name or ''}"
        ) or []

    def find_studio_children(self, studio_stash_id: str) -> list[dict]:
        logger.debug(f"TPDB does not support finding child studios for {studio_stash_id}.")
        return []

    def find_tag_id(self, tag_name: str) -> str | None:
        response = requests.get(
            f"https://api.theporndb.net/tags?q={tag_name}",
            headers=self.headers,
        )
        if response.status_code == 200:
            tags_data = response.json()
            for tag in tags_data.get("data", []):
                if tag.get("name", "").lower() == tag_name.lower():
                    return tag.get("id")
            logger.warning(f"Tag '{tag_name}' not found on TPDB.")
        else:
            logger.error(
                f"Query failed with status code {response.status_code}: {response.text}"
            )
        return None

    def _paginate_scenes(self, base_url: str):
        scenes = []
        page = 1
        separator = "&" if "?" in base_url else "?"
        while True:
            url = f"{base_url}{separator}page={page}&per_page=25"
            logger.debug(f"Querying scenes from {url}")
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                scenes_data = response.json()
                for scene_data in scenes_data.get("data", []):
                    scenes.append(self._convert_scene(scene_data))

                if scenes_data.get("meta", {}).get("last_page") == page:
                    break
                page += 1
            else:
                logger.error(
                    f"Query failed with status code {response.status_code}: {response.text}"
                )
                return None

        logger.debug(f"Found {len(scenes)} scenes.")
        return scenes

    @staticmethod
    def _convert_scene(scene_data: dict) -> dict:
        studio = {
            "id": scene_data.get("site", {}).get("uuid"),
            "name": scene_data.get("site", {}).get("name"),
        }
        if scene_data.get("site", {}).get("network"):
            studio["parent"] = {
                "id": scene_data.get("site", {}).get("network", {}).get("uuid"),
                "name": scene_data.get("site", {}).get("network", {}).get("name"),
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

        return {
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
