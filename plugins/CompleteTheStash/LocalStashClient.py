from stashapi.stashapp import StashInterface


class LocalStashClient:
    def __init__(self, server_connection, logger):
        self.local_stash = StashInterface(server_connection)
        self.logger = logger

    def get_configuration(self):
        return self.local_stash.get_configuration()

    def find_tag(self, tag_name):
        return self.local_stash.find_tag({"name": tag_name})

    def find_performers(self, performer_filter, filter):
        return self.local_stash.find_performers(performer_filter, filter)

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
        return self.local_stash.find_performer(performer_id, create, fragment)

    def create_scene(self, scene_data):
        return self.local_stash.create_scene(scene_data)

    def destroy_scene(self, scene_id):
        return self.local_stash.destroy_scene(scene_id)
