from stashapi.stashapp import StashInterface


class LocalStashClient:
    def __init__(self, server_connection: dict, logger):
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
        return self.local_stash.find_performers(performer_filter, filter)

    def find_scene_by_id(self, scene_id):
        return self.local_stash.find_scene(scene_id)

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
