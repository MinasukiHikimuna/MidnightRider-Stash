import requests
import stashapi.log as logger


class StashDbClient(object):
    def __init__(self, endpoint, api_key):
        self.endpoint = endpoint
        self.api_key = api_key

    def query_scenes(self, scene_id):
        query = """
            query FindScene($scene_id: ID!) {
                findScene(
                    id: $scene_id
                ) {
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
                        }
                    }
                    duration
                    code
                    tags {
                        id
                        name
                    }
                }
            }
        """
        result = self._gql_query(
            query, {"scene_id": scene_id}
        )
        return result

    def query_tags(self):
        query = """
            query QueryTags($page: Int!, $per_page: Int!) {
                queryTags(input: {
                    page: $page
                    per_page: $per_page
                }) {
                    count
                    tags {
                        id
                        name
                        description
                        aliases
                        deleted
                        created
                        updated
                        category {
                            id
                            name
                            group
                            description
                        }
                    }
                }
            }
        """
        per_page = 25
        page = 1
        all_tags = []
        total_count = None

        while True:
            result = self._gql_query(query, {"page": page, "per_page": per_page})
            if result is None or 'data' not in result or 'queryTags' not in result['data']:
                break

            tags_data = result['data']['queryTags']
            all_tags.extend(tags_data['tags'])

            if total_count is None:
                total_count = tags_data['count']

            if len(all_tags) >= total_count:
                break

            page += 1

        return all_tags

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
