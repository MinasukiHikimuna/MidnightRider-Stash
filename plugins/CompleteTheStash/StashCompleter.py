from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from constants import PERFORMERS_PER_PAGE

if TYPE_CHECKING:
    from LocalStashClient import LocalStashClient
    from MissingStashClient import MissingStashClient
    from StashboxClient import StashboxClient


class StashCompleter:
    def __init__(
        self,
        config,
        logger,
        stashbox_client: StashboxClient,
        local_stash_client: LocalStashClient,
        missing_stash_client: MissingStashClient,
    ):
        self.stashbox_client = stashbox_client
        self.local_stash_client = local_stash_client
        self.missing_stash_client = missing_stash_client
        self.config = config
        self.logger = logger

    def _get_stash_id(self, item: dict) -> str | None:
        """Extract stash_id from an item's stash_ids for the configured endpoint."""
        endpoint = self.config.get("stashboxEndpoint")
        return next(
            (sid["stash_id"] for sid in item.get("stash_ids", []) if sid.get("endpoint") == endpoint),
            None,
        )

    def compare_scenes(self, local_scenes, existing_missing_scenes, stashbox_scenes):
        local_scene_ids = {self._get_stash_id(scene) for scene in local_scenes}
        local_scene_ids.discard(None)
        self.logger.trace(f"Local scene IDs: {local_scene_ids}")
        existing_missing_scene_ids = {self._get_stash_id(scene) for scene in existing_missing_scenes}
        existing_missing_scene_ids.discard(None)
        self.logger.trace(f"Existing missing scene IDs: {existing_missing_scene_ids}")

        new_missing_scenes = [
            scene
            for scene in stashbox_scenes
            if scene["id"] not in local_scene_ids
            and scene["id"] not in existing_missing_scene_ids
        ]
        return new_missing_scenes

    def create_scene(self, scene, performer_ids, studio_id):
        code = scene["code"]
        title = scene["title"]
        studio_url = scene["urls"][0]["url"] if scene["urls"] else None
        date = scene["release_date"]
        cover_image = scene["images"][0]["url"] if scene["images"] else None
        stash_id = scene["id"]
        tags = scene["tags"]
        tag_ids = []

        for tag in tags:
            missing_tag = self.missing_stash_client.get_or_create_tag(tag["name"])
            tag_ids.append(missing_tag["id"])

        new_scene = {
            "title": title,
            "code": code,
            "details": scene["details"],
            "url": studio_url,
            "studio_id": studio_id,
            "performer_ids": performer_ids,
            "tag_ids": tag_ids,
            "cover_image": cover_image,
            "stash_ids": [
                {
                    "endpoint": self.config.get("stashboxEndpoint"),
                    "stash_id": stash_id,
                }
            ],
        }

        try:
            formatted_date = (
                datetime.date.fromisoformat(date).isoformat() if date else None
            )
            new_scene["date"] = formatted_date
        except ValueError:
            pass

        result = self.missing_stash_client.create_scene(new_scene)
        if result:
            return result["id"]

        self.logger.error(f"Failed to create scene '{title}'")
        return None

    def get_or_create_studio_by_stash_id(
        self, studio, parent_studio_id: int | None = None
    ):
        stash_id = studio["id"]
        studio_name = studio["name"]

        studios = self.missing_stash_client.find_studios(
            {
                "name": {
                    "value": studio_name,
                    "modifier": "EQUALS",
                },
                "stash_id_endpoint": {
                    "stash_id": stash_id,
                    "endpoint": self.config.get("stashboxEndpoint"),
                    "modifier": "EQUALS",
                },
            }
        )
        if studios:
            if len(studios) > 1:
                self.logger.warning(
                    f"Multiple studios found with stash ID {stash_id}. Using the first one."
                )

            studio_id = studios[0]["id"]
            self.logger.debug(
                f"Studio found with stash ID {stash_id} with ID: {studio_id}"
            )
            return studio_id

        studio_create_input = {
            "name": studio_name,
            "stash_ids": [
                {"stash_id": stash_id, "endpoint": self.config.get("stashboxEndpoint")}
            ],
        }

        if parent_studio_id:
            studio_create_input["parent_id"] = parent_studio_id

        studio_image = self.stashbox_client.query_studio_image(stash_id)
        if studio_image:
            studio_create_input["image"] = studio_image

        self.logger.debug(f"Creating studio: {studio_name}")
        created_studio = self.missing_stash_client.create_studio(studio_create_input)
        if created_studio:
            studio_id = created_studio["id"]
            self.logger.info(f"Studio created: {studio_name}")
            return studio_id

        self.logger.error(f"Failed to create studio '{studio_name}'")
        return None

    def get_or_create_missing_performer(
        self, local_performer: Any, performer_stash_id: str
    ) -> int | None:
        performer_in = self._convert_local_performer_to_missing_stash_input(local_performer)

        existing_performers = self.missing_stash_client.find_performers_by_stash_id(
            performer_stash_id
        )
        if existing_performers:
            if len(existing_performers) > 1:
                self.logger.warning(
                    f"Multiple performers found with stash ID {performer_stash_id}. Using the first one."
                )

            performer_id = existing_performers[0]["id"]
            self.logger.debug(
                f"Performer {performer_in['name']}: Matched with Stash ID {performer_stash_id} "
                f"to missing Stash ID {performer_id}"
            )

            performer_in["id"] = performer_id
            if performer_in.get("custom_fields"):
                performer_in["custom_fields"] = { "full": performer_in["custom_fields"] }
            self.missing_stash_client.update_performer(performer_in)
            return performer_id

        performer = self.missing_stash_client.create_performer(performer_in)
        if performer:
            self.logger.info(f"Performer created: {performer_in['name']} (stashbox ID: {performer_stash_id})")
            return performer["id"]
        self.logger.error(f"Failed to create performer '{performer_in['name']}'")
        return None

    def _convert_local_performer_to_missing_stash_input(self, local_performer):
        performer_in = local_performer.copy()
        del performer_in["id"]

        tag_ids = [self.missing_stash_client.get_or_create_tag(tag["name"])["id"] for tag in performer_in["tags"]]
        performer_in["tag_ids"] = tag_ids

        keys_to_delete = [
            "tags", "scenes", "scene_count",
            "image_count", "gallery_count", "performer_count",
            "created_at", "updated_at", "image_path",
            "o_counter",
            "groups", "group_count",
            "movies", "movie_count"
        ]
        for key_to_delete in keys_to_delete:
            if key_to_delete in performer_in:
                del performer_in[key_to_delete]

        return performer_in

    def find_selected_local_performers(self):
        selected_performer_tags = self.config.get("performerTags")
        selected_performer_tag_ids = []
        for tag in selected_performer_tags:
            tag_id = self.local_stash_client.find_tag(tag)
            if tag_id:
                selected_performer_tag_ids.append(tag_id["id"])

        performers = []
        page = 1
        self.logger.debug("Searching for local favorite performers...")
        while True:
            performer_filter = {
                "tags": {"value": selected_performer_tag_ids, "modifier": "INCLUDES"}
            }
            filter = {"page": page, "per_page": PERFORMERS_PER_PAGE}
            result = self.local_stash_client.find_performers(performer_filter, filter)
            performers.extend(result)
            if len(result) < PERFORMERS_PER_PAGE:
                break
            page += 1

        return performers

    def process_performers(self):
        selected_local_performers = self.find_selected_local_performers()
        selected_local_performers_with_stash_ids = []
        missing_performers_by_stash_id = {}

        for local_performer in selected_local_performers:
            local_performer_name = local_performer["name"]
            performer_stash_id = self._get_stash_id(local_performer)
            if not performer_stash_id:
                endpoint = self.config.get("stashboxEndpoint")
                self.logger.warning(
                    f"Performer {local_performer_name} does not have a Stashbox ID for endpoint {endpoint}. Skipping..."
                )
                continue

            selected_local_performers_with_stash_ids.append(local_performer)
            missing_performer_id = self.get_or_create_missing_performer(
                local_performer, performer_stash_id
            )

            missing_performers_by_stash_id[performer_stash_id] = missing_performer_id

        for local_performer in selected_local_performers_with_stash_ids:
            self.process_performer(
                local_performer["id"], missing_performers_by_stash_id
            )

        self._cleanup_duplicate_missing_scenes()

    def process_performer(
        self, local_performer_id: int, missing_performers_by_stash_id: dict[str, int]
    ):
        local_performer_details = self.local_stash_client.find_performer(
            local_performer_id
        )
        if not local_performer_details:
            self.logger.error("Failed to retrieve details for performer.")
            return

        self.logger.info(f"Performer {local_performer_details['name']}: Processing...")

        performer_stash_id = self._get_stash_id(local_performer_details)

        missing_performer_id = missing_performers_by_stash_id.get(performer_stash_id)
        missing_performer_details = self.missing_stash_client.find_performer(
            missing_performer_id
        )

        local_scenes = local_performer_details["scenes"]
        existing_missing_scenes = missing_performer_details["scenes"]

        stashbox_scenes = self.stashbox_client.query_scenes(performer_stash_id)
        filtered_stashbox_scenes = self._filter_scenes_by_tags(stashbox_scenes)

        destroyed_scenes_stash_ids = self._destroy_obsolete_scenes(
            local_scenes, existing_missing_scenes, filtered_stashbox_scenes
        )

        missing_scenes = self.compare_scenes(
            local_scenes, existing_missing_scenes, filtered_stashbox_scenes
        )

        created_scenes_stash_ids = self._create_missing_scenes(
            missing_scenes, missing_performers_by_stash_id
        )

        self._log_performer_summary(
            local_performer_details["name"], created_scenes_stash_ids, destroyed_scenes_stash_ids
        )

    def _filter_scenes_by_tags(self, stashbox_scenes: list) -> list:
        exclude_tags = self.config.get("sceneExcludeTags")
        if not exclude_tags:
            return stashbox_scenes

        filtered = []
        for scene in stashbox_scenes:
            if not scene["tags"]:
                filtered.append(scene)
            else:
                self.logger.debug(f"Scene ID: {scene['id']}")
                self.logger.debug(f"Scene title: {scene['title']}")
                self.logger.debug(f"Scene tags: {scene['tags']}")
                self.logger.debug(f"Exclude tags: {exclude_tags}")
                if not any(tag["name"] in exclude_tags for tag in scene["tags"]):
                    filtered.append(scene)
        return filtered

    def _destroy_obsolete_scenes(
        self, local_scenes, existing_missing_scenes, filtered_stashbox_scenes
    ) -> list[str]:
        stashbox_scene_ids = {scene["id"] for scene in filtered_stashbox_scenes}
        local_scene_stash_ids = {self._get_stash_id(scene) for scene in local_scenes}
        local_scene_stash_ids.discard(None)

        destroyed_ids = []
        for existing_missing_scene in existing_missing_scenes:
            stash_id = self._get_stash_id(existing_missing_scene)
            title = existing_missing_scene["title"]
            scene_id = existing_missing_scene["id"]

            if stash_id in local_scene_stash_ids:
                self.missing_stash_client.destroy_scene(scene_id)
                destroyed_ids.append(stash_id)
                self.logger.info(f"Scene {title} (ID: {scene_id}) destroyed.")
            elif stash_id not in stashbox_scene_ids:
                self.missing_stash_client.destroy_scene(scene_id)
                destroyed_ids.append(stash_id)
                self.logger.info(
                    f"Scene {title} (ID: {scene_id}) destroyed as it was no longer found in StashDB scenes."
                )
        return destroyed_ids

    def _create_missing_scenes(
        self, missing_scenes, missing_performers_by_stash_id: dict[str, int]
    ) -> list[str]:
        total_scenes = len(missing_scenes)
        created_ids = []
        for scene in missing_scenes:
            stash_id = scene["id"]

            # Check if scene already exists by stash_id (handles orphaned scenes not linked to performer)
            existing_scenes = self.missing_stash_client.find_scenes_by_stash_id(stash_id)
            if existing_scenes:
                self.logger.debug(
                    f"Scene {scene['title']} already exists with stash_id {stash_id}. Skipping..."
                )
                continue
            parent_studio_id = None
            if (
                "studio" in scene
                and "parent" in scene["studio"]
                and scene["studio"]["parent"]
            ):
                parent_studio_id = self.get_or_create_studio_by_stash_id(
                    scene["studio"]["parent"]
                )

            scene_studio_id = self.get_or_create_studio_by_stash_id(
                scene["studio"], parent_studio_id
            )

            scene_performer_stash_ids = [
                scene_performer["performer"]["id"]
                for scene_performer in scene["performers"]
            ]
            missing_performer_ids = [
                missing_performers_by_stash_id.get(sid)
                for sid in scene_performer_stash_ids
                if missing_performers_by_stash_id.get(sid) is not None
            ]

            created_scene_id = self.create_scene(
                scene, missing_performer_ids, scene_studio_id
            )
            if created_scene_id:
                self.logger.info(
                    f"Scene {scene['title']} (ID: {created_scene_id}) created"
                )
                created_ids.append(scene["id"])
                progress = len(created_ids) / total_scenes
                self.logger.progress(progress)
        return created_ids

    def _log_performer_summary(
        self, performer_name: str, created_ids: list, destroyed_ids: list
    ):
        if created_ids or destroyed_ids:
            num_created = len(created_ids)
            num_destroyed = len(destroyed_ids)
            created_msg = f"{num_created} new missing scenes created. " if num_created > 0 else ""
            destroyed_msg = f"{num_destroyed} previously missing scenes destroyed." if num_destroyed > 0 else ""
            msg = f"{created_msg}{destroyed_msg}" if created_msg and destroyed_msg else created_msg or destroyed_msg
            self.logger.info(f"Performer {performer_name}: {msg}")
        else:
            self.logger.info(f"Performer {performer_name}: No changes detected.")

    def _log_process_summary(self, process_name: str, num_created: int):
        if num_created > 0:
            self.logger.info(f"{process_name}: {num_created} new missing scenes created.")
        else:
            self.logger.info(f"{process_name}: No new scenes to create.")

    def _cleanup_duplicate_missing_scenes(self):
        """Destroy scenes from missing Stash that now exist in local Stash."""
        scenes_in_local_stash = self.local_stash_client.find_all_scenes()
        scenes_in_missing_stash = self.missing_stash_client.find_all_scenes()

        local_scene_stash_ids = {self._get_stash_id(scene) for scene in scenes_in_local_stash}
        local_scene_stash_ids.discard(None)

        scenes_to_destroy = []
        for missing_scene in scenes_in_missing_stash:
            missing_scene_stash_id = self._get_stash_id(missing_scene)
            if missing_scene_stash_id in local_scene_stash_ids:
                scenes_to_destroy.append(missing_scene)

        for scene in scenes_to_destroy:
            self.missing_stash_client.destroy_scene(scene["id"])
            self.logger.info(f"Destroyed missing scene: {scene['title']} (ID: {scene['id']})")

        if len(scenes_to_destroy) > 0:
            self.logger.info(f"Destroyed {len(scenes_to_destroy)} scenes from missing stash that exist in local stash.")

    def _ensure_performers_for_scenes(self, scenes: list) -> dict[str, int]:
        """Create/find all performers referenced in scenes, returns {stash_id: missing_id} map."""
        missing_performers_by_stash_id: dict[str, int] = {}
        for scene in scenes:
            for scene_performer in scene.get("performers", []):
                performer = scene_performer["performer"]
                performer_stash_id = performer["id"]
                if performer_stash_id in missing_performers_by_stash_id:
                    continue
                missing_id = self._get_or_create_missing_performer_from_stashbox(
                    performer, performer_stash_id
                )
                if missing_id is not None:
                    missing_performers_by_stash_id[performer_stash_id] = missing_id
        return missing_performers_by_stash_id

    def _get_or_create_missing_performer_from_stashbox(
        self, stashbox_performer: dict, performer_stash_id: str
    ) -> int | None:
        """Find or create a performer in missing Stash from stashbox performer data."""
        existing_performers = self.missing_stash_client.find_performers_by_stash_id(
            performer_stash_id
        )
        if existing_performers:
            return existing_performers[0]["id"]

        performer_name = stashbox_performer.get("name", "Unknown")
        image_url = None
        if stashbox_performer.get("images"):
            image_url = stashbox_performer["images"][0].get("url")

        performer_in = {
            "name": performer_name,
            "gender": stashbox_performer.get("gender"),
            "image": image_url,
            "stash_ids": [
                {
                    "stash_id": performer_stash_id,
                    "endpoint": self.config.get("stashboxEndpoint"),
                }
            ],
        }

        if stashbox_performer.get("disambiguation"):
            performer_in["disambiguation"] = stashbox_performer["disambiguation"]

        performer = self.missing_stash_client.create_performer(performer_in)
        if performer:
            self.logger.info(f"Performer created: {performer_name} (stashbox ID: {performer_stash_id})")
            return performer["id"]
        self.logger.error(f"Failed to create performer '{performer_name}'")
        return None

    def _resolve_tag_ids(self) -> list[str]:
        """Resolve configured tag names to local Stash tag IDs."""
        selected_tags = self.config.get("performerTags")
        tag_ids = []
        for tag_name in selected_tags:
            tag = self.local_stash_client.find_tag(tag_name)
            if tag:
                tag_ids.append(tag["id"])
            else:
                self.logger.warning(f"Tag '{tag_name}' not found in local Stash.")
        return tag_ids

    def _deduplicate_scenes(self, scenes: list) -> list:
        """Deduplicate scenes by stashbox ID."""
        seen = set()
        unique = []
        for scene in scenes:
            if scene["id"] not in seen:
                seen.add(scene["id"])
                unique.append(scene)
        return unique

    def find_selected_local_studios(self):
        tag_ids = self._resolve_tag_ids()
        if not tag_ids:
            self.logger.warning("No valid tags found for studio selection.")
            return []
        return self.local_stash_client.find_studios_by_tags(tag_ids)

    def process_studios(self):
        selected_studios = self.find_selected_local_studios()
        if not selected_studios:
            self.logger.info("No studios found with configured tags.")
            return

        endpoint = self.config.get("stashboxEndpoint")
        all_studio_stash_ids = []
        for studio in selected_studios:
            studio_stash_id = self._get_stash_id(studio)
            if not studio_stash_id:
                self.logger.warning(
                    f"Studio {studio['name']} does not have a Stashbox ID for endpoint {endpoint}. Skipping..."
                )
                continue

            all_studio_stash_ids.append(studio_stash_id)
            self.logger.info(f"Studio {studio['name']}: Collecting sub-studios...")
            children = self.stashbox_client.find_studio_children(studio_stash_id)
            for child in children:
                all_studio_stash_ids.append(child["id"])
                self.logger.debug(f"  Sub-studio: {child['name']} ({child['id']})")

        if not all_studio_stash_ids:
            self.logger.info("No studios with valid Stashbox IDs found.")
            return

        self.logger.info(f"Querying scenes for {len(all_studio_stash_ids)} studio(s)...")
        stashbox_scenes = self.stashbox_client.query_scenes_by_studio(all_studio_stash_ids)
        stashbox_scenes = self._deduplicate_scenes(stashbox_scenes)
        self.logger.info(f"Found {len(stashbox_scenes)} unique scenes from StashDB.")

        filtered_scenes = self._filter_scenes_by_tags(stashbox_scenes)

        local_scenes = self.local_stash_client.find_all_scenes()
        existing_missing_scenes = self.missing_stash_client.find_all_scenes()
        missing_scenes = self.compare_scenes(local_scenes, existing_missing_scenes, filtered_scenes)
        self.logger.info(f"Found {len(missing_scenes)} new missing scenes to create.")

        missing_performers_by_stash_id = self._ensure_performers_for_scenes(missing_scenes)
        created_ids = self._create_missing_scenes(missing_scenes, missing_performers_by_stash_id)
        self._cleanup_duplicate_missing_scenes()
        self._log_process_summary("Studios", len(created_ids))

    def process_tags(self):
        tag_ids = self._resolve_tag_ids()
        if not tag_ids:
            self.logger.warning("No valid tags found for tag selection.")
            return

        all_stashbox_scenes = []
        for parent_tag_id in tag_ids:
            child_tags = self.local_stash_client.find_child_tags(parent_tag_id)
            if not child_tags:
                self.logger.info(f"No child tags found for tag ID {parent_tag_id}.")
                continue

            for child_tag in child_tags:
                tag_name = child_tag["name"]
                self.logger.info(f"Tag '{tag_name}': Looking up on StashDB...")
                stashbox_tag_id = self.stashbox_client.find_tag_id(tag_name)
                if not stashbox_tag_id:
                    self.logger.warning(f"Tag '{tag_name}' not found on StashDB. Skipping...")
                    continue

                self.logger.info(f"Tag '{tag_name}': Querying scenes...")
                scenes = self.stashbox_client.query_scenes_by_tag(stashbox_tag_id, tag_name)
                self.logger.info(f"Tag '{tag_name}': Found {len(scenes)} scenes.")
                all_stashbox_scenes.extend(scenes)

        all_stashbox_scenes = self._deduplicate_scenes(all_stashbox_scenes)
        self.logger.info(f"Found {len(all_stashbox_scenes)} unique scenes from StashDB.")

        filtered_scenes = self._filter_scenes_by_tags(all_stashbox_scenes)

        local_scenes = self.local_stash_client.find_all_scenes()
        existing_missing_scenes = self.missing_stash_client.find_all_scenes()
        missing_scenes = self.compare_scenes(local_scenes, existing_missing_scenes, filtered_scenes)
        self.logger.info(f"Found {len(missing_scenes)} new missing scenes to create.")

        missing_performers_by_stash_id = self._ensure_performers_for_scenes(missing_scenes)
        created_ids = self._create_missing_scenes(missing_scenes, missing_performers_by_stash_id)
        self._cleanup_duplicate_missing_scenes()
        self._log_process_summary("Tags", len(created_ids))

    def process_scene_by_id(self, scene_id: int):
        scene = self.local_stash_client.find_scene_by_id(scene_id)
        if not scene:
            self.logger.error(f"Scene {scene_id} not found.")
            return

        stashbox_id = self._get_stash_id(scene)
        if not stashbox_id:
            self.logger.error(f"Scene {scene_id} does not have a stashbox ID.")
            return

        self.process_scene_by_stashbox_id(stashbox_id)

    def process_scene_by_stashbox_id(self, stashbox_id: str):
        scenes = self.missing_stash_client.find_scenes_by_stash_id(stashbox_id)
        if scenes:
            if len(scenes) > 1:
                self.logger.warning(
                    f"Multiple scenes found with stashbox ID {stashbox_id}. Using the first one."
                )

            scene = scenes[0]
            self.missing_stash_client.destroy_scene(scene["id"])
            self.logger.info(
                f"Scene {scene['title']} (ID: {scene['id']}, Stashbox ID: {stashbox_id}) "
                f"destroyed as it was found in the local Stash."
            )
