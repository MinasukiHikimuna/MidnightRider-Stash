from stashapi.stashapp import StashInterface


class MissingStashClient:
    def __init__(self, scheme, host, port, api_key, stash_db_endpoint, logger):
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

    def get_configuration(self):
        return self.missing_stash.get_configuration()

    def get_or_create_tag(self, tag_name: str) -> dict:
        return self.missing_stash.find_tag({"name": tag_name}, True)

    def create_scene(self, scene_data):
        return self.missing_stash.create_scene(scene_data)

    def destroy_scene(self, scene_id: int) -> None:
        scene = self.missing_stash.find_scene(scene_id)
        if scene:
            return self.missing_stash.destroy_scene(scene_id)

    def find_performer(self, performer_id: int) -> dict:
        create = False
        fragment = """
            id
            name
            stash_ids {
                stash_id
                endpoint
            }
            scenes {
                id
                title
                stash_ids {
                    stash_id
                    endpoint
                }
            }
            """
        return self.missing_stash.find_performer(performer_id, create, fragment)

    def find_studios(self, studio_filter):
        return self.missing_stash.find_studios(studio_filter)

    def create_studio(self, studio_data):
        return self.missing_stash.create_studio(studio_data)

    def create_performer(self, performer_data):
        return self.missing_stash.create_performer(performer_data)
    
    def update_performer(self, performer_data):
        return self.missing_stash.update_performer(performer_data)

    def find_scenes_by_stash_id(self, stash_id: str):
        return self.missing_stash.find_scenes(
            {
                "stash_id_endpoint": {
                    "stash_id": stash_id,
                    "endpoint": self.stash_db_endpoint,
                    "modifier": "EQUALS",
                }
            }
        )

    def find_performers_by_stash_id(self, stash_id: str):
        return self.missing_stash.find_performers(
            {
                "stash_id_endpoint": {
                    "stash_id": stash_id,
                    "endpoint": self.stash_db_endpoint,
                    "modifier": "EQUALS",
                }
            }
        )

    def find_all_scenes(self):
        return self.missing_stash.find_scenes(fragment="id title stash_ids { stash_id endpoint }")
