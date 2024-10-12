from stashapi.stashapp import StashInterface


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
            import requests

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
                        import base64
                        import mimetypes

                        content_type = response.headers.get('Content-Type', '')
                        image_type = mimetypes.guess_extension(content_type)
                        
                        if image_type:
                            image_type = image_type.lstrip('.')  # Remove leading dot
                        else:
                            image_type = 'jpeg'  # Default to jpeg if type can't be determined
                        
                        image_data = base64.b64encode(response.content).decode('utf-8')
                        data_url = f"data:image/{image_type};base64,{image_data}"
                        performer['image'] = data_url
                        self.logger.debug(f"Downloaded image for performer {performer['name']}")
                    except requests.RequestException as e:
                        self.logger.error(f"Failed to download image for performer {performer['name']}: {str(e)}")
        return performers

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

    def find_all_scenes(self):
        return self.local_stash.find_scenes(fragment="id title stash_ids { stash_id endpoint }")
