from datetime import datetime

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

    def compare_scenes(self, local_scenes, existing_missing_scenes, stashbox_scenes):
        local_scene_ids = {
            stash_id["stash_id"]
            for scene in local_scenes
            for stash_id in scene["stash_ids"]
            if stash_id.get("endpoint") == self.config.get("stashboxEndpoint")
        }
        self.logger.trace(f"Local scene IDs: {local_scene_ids}")
        existing_missing_scene_ids = {
            stash_id["stash_id"]
            for scene in existing_missing_scenes
            for stash_id in scene["stash_ids"]
            if stash_id.get("endpoint") == self.config.get("stashboxEndpoint")
        }
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
                datetime.strptime(date, "%Y-%m-%d").date().isoformat() if date else None
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
        if studios and len(studios) > 0:
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
        studio = self.missing_stash_client.create_studio(studio_create_input)
        if studio:
            studio_id = studio["id"]
            self.logger.info(f"Studio created: {studio_name}")
            return studio_id

        self.logger.error(f"Failed to create studio '{studio_name}'")
        return None

    def get_or_create_missing_performer(
        self, local_performer: any, performer_stash_id: str
    ) -> int:
        performer_in = self._convert_local_performer_to_missing_stash_input(local_performer)
        
        existing_performers = self.missing_stash_client.find_performers_by_stash_id(
            performer_stash_id
        )
        if existing_performers and len(existing_performers) > 0:
            if len(existing_performers) > 1:
                self.logger.warning(
                    f"Multiple performers found with stash ID {performer_stash_id}. Using the first one."
                )

            performer_id = existing_performers[0]["id"]
            self.logger.debug(
                f"Performer {performer_in['name']}: Matched with Stash ID {performer_stash_id} to missing Stash ID {performer_id}"
            )
            
            performer_in['id'] = performer_id
            if performer_in['custom_fields']:
                performer_in['custom_fields'] = { "full": performer_in['custom_fields'] }
            self.missing_stash_client.update_performer(performer_in)            
            return performer_id

        performer = self.missing_stash_client.create_performer(performer_in)
        if performer:
            self.logger.info(f"Performer created: {performer_in['name']}")
            return performer["id"]
        self.logger.error(f"Failed to create performer '{performer_in['name']}'")
        return None

    def _convert_local_performer_to_missing_stash_input(self, local_performer):
        performer_in = local_performer.copy()
        del performer_in['id']
        
        tag_ids = [self.missing_stash_client.get_or_create_tag(tag['name'])['id'] for tag in performer_in['tags']]
        performer_in['tag_ids'] = tag_ids
        
        keys_to_delete = [
            'tags', 'scenes', 'scene_count',
            'image_count', 'gallery_count', 'performer_count',
            'created_at', 'updated_at', 'image_path',
            'o_counter',
            'groups', 'group_count',
            'movies', 'movie_count'
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
        self.logger.debug(f"Searching for local favorite performers...")
        while True:
            performer_filter = {
                "tags": {"value": selected_performer_tag_ids, "modifier": "INCLUDES"}
            }
            filter = {"page": page, "per_page": 25}
            result = self.local_stash_client.find_performers(performer_filter, filter)
            performers.extend(result)
            if len(result) < 25:
                break
            page += 1

        return performers

    def process_performers(self):
        selected_local_performers = self.find_selected_local_performers()
        selected_local_performers_with_stash_ids = []
        missing_performers_by_stash_id = {}

        for local_performer in selected_local_performers:
            local_performer_name = local_performer["name"]
            performer_stash_id: str = next(
                (
                    sid["stash_id"]
                    for sid in local_performer["stash_ids"]
                    if sid.get("endpoint") == self.config.get("stashboxEndpoint")
                ),
                None,
            )
            if not performer_stash_id:
                self.logger.warning(
                    f"Performer {local_performer_name} does not have a Stashbox ID for endpoint {self.config.get('stashboxEndpoint')}. Skipping..."
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

        # Destroy scenes which weren't associated with a performer in local Stash but existed both in local and missing Stash.
        scenes_in_local_stash = self.local_stash_client.find_all_scenes()
        scenes_in_missing_stash = self.missing_stash_client.find_all_scenes()
        
        # Match scenes in local and missing stashes by stash_id
        local_scene_stash_ids = {
            stash_id["stash_id"]
            for scene in scenes_in_local_stash
            for stash_id in scene["stash_ids"]
            if stash_id.get("endpoint") == self.config.get("stashboxEndpoint")
        }

        scenes_to_destroy = []
        for missing_scene in scenes_in_missing_stash:
            missing_scene_stash_id = next(
                (
                    stash_id["stash_id"]
                    for stash_id in missing_scene["stash_ids"]
                    if stash_id.get("endpoint") == self.config.get("stashboxEndpoint")
                ),
                None,
            )
            if missing_scene_stash_id in local_scene_stash_ids:
                scenes_to_destroy.append(missing_scene)

        # Destroy missing scenes that exist in local stash
        for scene in scenes_to_destroy:
            self.missing_stash_client.destroy_scene(scene["id"])
            self.logger.info(f"Destroyed missing scene: {scene['title']} (ID: {scene['id']})")

        if len(scenes_to_destroy) > 0:
            self.logger.info(f"Destroyed {len(scenes_to_destroy)} scenes from missing stash that exist in local stash.")

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

        performer_stash_id = next(
            (
                sid["stash_id"]
                for sid in local_performer_details["stash_ids"]
                if sid.get("endpoint") == self.config.get("stashboxEndpoint")
            ),
            None,
        )

        missing_performer_id = missing_performers_by_stash_id.get(performer_stash_id)
        missing_performer_details = self.missing_stash_client.find_performer(
            missing_performer_id
        )

        local_scenes = local_performer_details["scenes"]
        existing_missing_scenes = missing_performer_details["scenes"]

        stashbox_scenes = self.stashbox_client.query_scenes(performer_stash_id)
        filtered_stashbox_scenes = []
        exclude_tags = self.config.get("sceneExcludeTags")
        if exclude_tags is None or not exclude_tags:
            filtered_stashbox_scenes = stashbox_scenes
        else:
            for scene in stashbox_scenes:
                if scene["tags"] is None or not scene["tags"]:
                    filtered_stashbox_scenes.append(scene)
                else:
                    self.logger.debug(f"Scene ID: {scene['id']}")
                    self.logger.debug(f"Scene title: {scene['title']}")
                    self.logger.debug(f"Scene tags: {scene['tags']}")
                    self.logger.debug(f"Exclude tags: {exclude_tags}")
                    if not any(tag["name"] in exclude_tags for tag in scene["tags"]):
                        filtered_stashbox_scenes.append(scene)

        # Create a set of stashbox scene IDs for quick lookup
        stashbox_scene_ids = {scene["id"] for scene in filtered_stashbox_scenes}

        destroyed_scenes_stash_ids = []
        for local_scene in local_scenes:
            scene_stash_id = next(
                (
                    sid["stash_id"]
                    for sid in local_scene["stash_ids"]
                    if sid.get("endpoint") == self.config.get("stashboxEndpoint")
                ),
                None,
            )
            for existing_missing_scene in existing_missing_scenes:
                existing_missing_scene_stash_id = next(
                    (
                        sid["stash_id"]
                        for sid in existing_missing_scene["stash_ids"]
                        if sid.get("endpoint") == self.config.get("stashboxEndpoint")
                    ),
                    None,
                )
                if scene_stash_id == existing_missing_scene_stash_id:
                    self.missing_stash_client.destroy_scene(
                        existing_missing_scene["id"]
                    )
                    destroyed_scenes_stash_ids.append(existing_missing_scene_stash_id)
                    self.logger.info(
                        f"Scene {existing_missing_scene['title']} (ID: {existing_missing_scene['id']}) destroyed."
                    )

        # Destroy existing missing scenes that are not in stashdb_scenes
        for existing_missing_scene in existing_missing_scenes:
            existing_missing_scene_stash_id = next(
                (
                    sid["stash_id"]
                    for sid in existing_missing_scene["stash_ids"]
                    if sid.get("endpoint") == self.config.get("stashboxEndpoint")
                ),
                None,
            )
            if existing_missing_scene_stash_id not in stashbox_scene_ids:
                self.missing_stash_client.destroy_scene(existing_missing_scene["id"])
                destroyed_scenes_stash_ids.append(existing_missing_scene_stash_id)
                self.logger.info(
                    f"Scene {existing_missing_scene['title']} (ID: {existing_missing_scene['id']}) destroyed as it was no longer found in StashDB scenes."
                )

        missing_scenes = self.compare_scenes(
            local_scenes, existing_missing_scenes, filtered_stashbox_scenes
        )

        total_scenes = len(missing_scenes)
        created_scenes_stash_ids = []
        for scene in missing_scenes:
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

            # Create scene and link it to the new studio
            created_scene_id = self.create_scene(
                scene, missing_performer_ids, scene_studio_id
            )
            if created_scene_id:
                self.logger.info(
                    f"Scene {scene['title']} (ID: {created_scene_id}) created"
                )

                # Update progress
                created_scene_stash_id = scene["id"]
                created_scenes_stash_ids.append(created_scene_stash_id)
                progress = len(created_scenes_stash_ids) / total_scenes
                self.logger.progress(progress)

        if len(created_scenes_stash_ids) > 0 or len(destroyed_scenes_stash_ids) > 0:
            created_msg = f"{len(created_scenes_stash_ids)} new missing scenes created. " if len(created_scenes_stash_ids) > 0 else ""
            destroyed_msg = f"{len(destroyed_scenes_stash_ids)} previously missing scenes destroyed." if len(destroyed_scenes_stash_ids) > 0 else ""
            
            if created_msg and destroyed_msg:
                msg = f"{created_msg}{destroyed_msg}"
            else:
                msg = created_msg or destroyed_msg
            
            self.logger.info(f"Performer {local_performer_details['name']}: {msg}.")
        else:
            self.logger.info(f"Performer {local_performer_details['name']}: No changes detected.")

    def process_scene_by_id(self, scene_id: int):
        scene = self.local_stash_client.find_scene_by_id(scene_id)
        if not scene:
            self.logger.error(f"Scene {scene_id} not found.")
            return

        stashbox_id = next(
            (
                sid["stash_id"]
                for sid in scene["stash_ids"]
                if sid.get("endpoint") == self.config.get("stashboxEndpoint")
            ),
            None,
        )
        if not stashbox_id:
            self.logger.error(f"Scene {scene_id} does not have a stashbox ID.")
            return

        self.process_scene_by_stashbox_id(stashbox_id)

    def process_scene_by_stashbox_id(self, stashbox_id: str):
        scenes = self.missing_stash_client.find_scenes_by_stash_id(stashbox_id)
        if scenes and len(scenes) > 0:
            if len(scenes) > 1:
                self.logger.warning(
                    f"Multiple scenes found with stashbox ID {stashbox_id}. Using the first one."
                )

            scene = scenes[0]
            self.missing_stash_client.destroy_scene(scene["id"])
            self.logger.info(
                f"Scene {scene['title']} (ID: {scene['id']}, Stashbox ID: {stashbox_id}) destroyed as it was found in the local Stash."
            )
