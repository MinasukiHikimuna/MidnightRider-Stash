# GraphQL query fragments and queries

# Performer fragment for finding local/missing performers
PERFORMER_FRAGMENT = """
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

# Scene fragment for finding scenes by stash_id
SCENE_FRAGMENT = "id title stash_ids { stash_id endpoint }"

# StashDB Queries
FIND_PERFORMER_QUERY = """
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

FIND_STUDIO_QUERY = """
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

QUERY_SCENES = """
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
