import json
import os
import sys
import stashapi.log as logger
from datetime import datetime

from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashDbClient import StashDbClient

# Ensure the script can locate config.py
script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(script_dir)

import config  # Import the configuration


stashdb_client = StashDbClient(
    config.STASHDB_ENDPOINT, config.STASHDB_API_KEY, config.EXCLUDE_TAGS
)
local_stash_client = LocalStashClient(
    config.LOCAL_GQL_SCHEME,
    config.LOCAL_GQL_HOST,
    config.LOCAL_GQL_PORT,
    config.LOCAL_API_KEY,
    logger,
)
missing_stash_client = MissingStashClient(
    config.MISSING_GQL_SCHEME,
    config.MISSING_GQL_HOST,
    config.MISSING_GQL_PORT,
    config.MISSING_API_KEY,
    config.STASHDB_ENDPOINT,
    logger,
)


def compare_scenes(local_scenes, existing_missing_scenes, stashdb_scenes):
    local_scene_ids = {
        stash_id["stash_id"]
        for scene in local_scenes
        for stash_id in scene["stash_ids"]
        if stash_id.get("endpoint") == config.STASHDB_ENDPOINT
    }
    logger.trace(f"Local scene IDs: {local_scene_ids}")
    existing_missing_scene_ids = {
        stash_id["stash_id"]
        for scene in existing_missing_scenes
        for stash_id in scene["stash_ids"]
        if stash_id.get("endpoint") == config.STASHDB_ENDPOINT
    }
    logger.trace(f"Existing missing scene IDs: {existing_missing_scene_ids}")

    new_missing_scenes = [
        scene
        for scene in stashdb_scenes
        if scene["id"] not in local_scene_ids
        and scene["id"] not in existing_missing_scene_ids
    ]
    return new_missing_scenes


def create_scene(scene, performer_ids, studio_id):
    code = scene["code"]
    title = scene["title"]
    studio_url = scene["urls"][0]["url"] if scene["urls"] else None
    date = scene["release_date"]
    cover_image = scene["images"][0]["url"] if scene["images"] else None
    stash_id = scene["id"]
    tags = scene["tags"]
    tag_ids = []

    for tag in tags:
        missing_tag = missing_stash_client.get_or_create_tag(tag["name"])
        tag_ids.append(missing_tag["id"])

    try:
        # Ensure the date is in the correct format
        formatted_date = (
            datetime.strptime(date, "%Y-%m-%d").date().isoformat() if date else None
        )
    except ValueError:
        logger.error(
            f"Invalid date format for scene '{title}': {date} (StashDB ID: {stash_id})"
        )
        return None

    result = missing_stash_client.create_scene(
        {
            "title": title,
            "code": code,
            "details": scene["details"],
            "url": studio_url,
            "date": formatted_date,
            "studio_id": studio_id,
            "performer_ids": performer_ids,
            "tag_ids": tag_ids,
            "cover_image": cover_image,
            "stash_ids": [{"endpoint": config.STASHDB_ENDPOINT, "stash_id": stash_id}],
        }
    )

    if result:
        return result["id"]

    logger.error(f"Failed to create scene '{title}'")
    return None


def get_or_create_studio_by_stash_id(studio, parent_studio_id: int | None = None):
    stash_id = studio["id"]
    studio_name = studio["name"]

    studios = missing_stash_client.find_studios(
        {
            "name": {
                "value": studio_name,
                "modifier": "EQUALS",
            },
            "stash_id_endpoint": {
                "stash_id": stash_id,
                "endpoint": config.STASHDB_ENDPOINT,
                "modifier": "EQUALS",
            },
        }
    )
    if studios and len(studios) > 0:
        if len(studios) > 1:
            logger.warning(
                f"Multiple studios found with stash ID {stash_id}. Using the first one."
            )

        studio_id = studios[0]["id"]
        logger.debug(f"Studio found with stash ID {stash_id} with ID: {studio_id}")
        return studio_id

    studio_create_input = {
        "name": studio_name,
        "stash_ids": [{"stash_id": stash_id, "endpoint": config.STASHDB_ENDPOINT}],
    }

    if parent_studio_id:
        studio_create_input["parent_id"] = parent_studio_id

    studio_image = stashdb_client.query_studio_image(stash_id)
    if studio_image:
        studio_create_input["image"] = studio_image

    logger.debug(f"Creating studio: {studio_name}")
    studio = missing_stash_client.create_studio(studio_create_input)
    if studio:
        studio_id = studio["id"]
        logger.info(f"Studio created: {studio_name}")
        return studio_id

    logger.error(f"Failed to create studio '{studio_name}'")
    return None


def get_or_create_missing_performer(
    performer_name: str, performer_stash_id: str
) -> int:
    existing_performers = missing_stash_client.find_performers_by_stash_id(
        performer_stash_id
    )
    if existing_performers and len(existing_performers) > 0:
        if len(existing_performers) > 1:
            logger.warning(
                f"Multiple performers found with stash ID {performer_stash_id}. Using the first one."
            )

        performer_id = existing_performers[0]["id"]
        logger.debug(
            f"Performer {performer_name}: Matched with Stash ID {performer_stash_id} to missing Stash ID {performer_id}"
        )
        return performer_id

    image_url = stashdb_client.query_performer_image(performer_stash_id)

    performer_in = {
        "name": performer_name,
        "stash_ids": [
            {"stash_id": performer_stash_id, "endpoint": config.STASHDB_ENDPOINT}
        ],
    }
    if image_url:
        performer_in["image"] = image_url

    performer = missing_stash_client.create_performer(performer_in)
    if performer:
        logger.info(f"Performer created: {performer_name}")
        return performer["id"]
    logger.error(f"Failed to create performer '{performer_name}'")
    return None


def find_selected_local_performers():
    selected_performer_tags = config.PERFORMER_TAGS
    selected_performer_tag_ids = []
    for tag in selected_performer_tags:
        tag_id = local_stash_client.find_tag(tag)
        if tag_id:
            selected_performer_tag_ids.append(tag_id["id"])

    performers = []
    page = 1
    logger.debug(f"Searching for local favorite performers...")
    while True:
        performer_filter = {
            "tags": {"value": selected_performer_tag_ids, "modifier": "INCLUDES"}
        }
        filter = {"page": page, "per_page": 25}
        result = local_stash_client.find_performers(performer_filter, filter)
        performers.extend(result)
        if len(result) < 25:
            break
        page += 1

    return performers


def process_performers():
    selected_local_performers = find_selected_local_performers()
    missing_performers_by_stash_id = {}

    for local_performer in selected_local_performers:
        local_performer_name = local_performer["name"]
        performer_stash_id: str = next(
            (
                sid["stash_id"]
                for sid in local_performer["stash_ids"]
                if sid.get("endpoint") == config.STASHDB_ENDPOINT
            ),
            None,
        )
        missing_performer_id = get_or_create_missing_performer(
            local_performer_name, performer_stash_id
        )

        missing_performers_by_stash_id[performer_stash_id] = missing_performer_id

    for local_performer in selected_local_performers:
        process_performer(local_performer["id"], missing_performers_by_stash_id)


def process_performer(
    local_performer_id: int, missing_performers_by_stash_id: dict[str, int]
):
    local_performer_details = local_stash_client.find_performer(local_performer_id)
    if not local_performer_details:
        logger.error("Failed to retrieve details for performer.")
        return

    logger.info(f"Performer {local_performer_details['name']}: Processing...")

    performer_stash_id = next(
        (
            sid["stash_id"]
            for sid in local_performer_details["stash_ids"]
            if sid.get("endpoint") == config.STASHDB_ENDPOINT
        ),
        None,
    )

    missing_performer_id = missing_performers_by_stash_id.get(performer_stash_id)
    missing_performer_details = missing_stash_client.find_performer(
        missing_performer_id
    )

    local_scenes = local_performer_details["scenes"]
    existing_missing_scenes = missing_performer_details["scenes"]

    stashdb_scenes = stashdb_client.query_scenes(performer_stash_id)

    destroyed_scenes_stash_ids = []
    for local_scene in local_scenes:
        scene_stash_id = next(
            (
                sid["stash_id"]
                for sid in local_scene["stash_ids"]
                if sid.get("endpoint") == config.STASHDB_ENDPOINT
            ),
            None,
        )
        for existing_missing_scene in existing_missing_scenes:
            existing_missing_scene_stash_id = next(
                (
                    sid["stash_id"]
                    for sid in existing_missing_scene["stash_ids"]
                    if sid.get("endpoint") == config.STASHDB_ENDPOINT
                ),
                None,
            )
            if scene_stash_id == existing_missing_scene_stash_id:
                missing_stash_client.destroy_scene(existing_missing_scene["id"])
                destroyed_scenes_stash_ids.append(existing_missing_scene_stash_id)
                logger.debug(
                    f"Scene {existing_missing_scene['title']} (ID: {existing_missing_scene['id']}) destroyed."
                )

    missing_scenes = compare_scenes(
        local_scenes, existing_missing_scenes, stashdb_scenes
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
            parent_studio_id = get_or_create_studio_by_stash_id(
                scene["studio"]["parent"]
            )

        scene_studio_id = get_or_create_studio_by_stash_id(
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
        created_scene_id = create_scene(scene, missing_performer_ids, scene_studio_id)
        if created_scene_id:
            logger.info(f"Scene {scene['title']} (ID: {created_scene_id}) created")

            # Update progress
            created_scene_stash_id = scene["id"]
            created_scenes_stash_ids.append(created_scene_stash_id)
            progress = len(created_scenes_stash_ids) / total_scenes
            logger.progress(progress)

    if len(created_scenes_stash_ids) == 0 and len(destroyed_scenes_stash_ids) == 0:
        logger.info(
            f"Performer {local_performer_details['name']}: No changes detected."
        )
        return

    logger.info(
        f"Performer {local_performer_details['name']}: {len(destroyed_scenes_stash_ids)} previously missing scenes destroyed and {len(created_scenes_stash_ids)} new missing scenes created."
    )


def process_updated_scene(stash_id: str):
    scenes = missing_stash_client.find_scenes_by_stash_id(stash_id)
    if scenes and len(scenes) > 0:
        if len(scenes) > 1:
            logger.warning(
                f"Multiple scenes found with stash ID {stash_id}. Using the first one."
            )

        scene = scenes[0]
        missing_stash_client.destroy_scene(scene["id"])
        logger.debug(f"Scene {scene['title']} (ID: {scene['id']}) destroyed.")


def check_stash_instances_are_unique():
    if (
        config.LOCAL_GQL_SCHEME == config.MISSING_GQL_SCHEME
        and config.LOCAL_GQL_HOST == config.MISSING_GQL_HOST
        and config.LOCAL_GQL_PORT == config.MISSING_GQL_PORT
    ):
        logger.error(
            "Local and missing Stash instances are the same. Please create a different instance for missing Stash."
        )
        sys.exit(1)


def check_performer_tags_are_configured():
    if not config.PERFORMER_TAGS:
        logger.error("No performer tags are configured.")
        sys.exit(1)


def compare_performer_scenes():
    check_stash_instances_are_unique()
    check_performer_tags_are_configured()

    if os.getenv("FAKE_INPUT"):
        from fakeInput import fake_input

        json_input = fake_input[os.getenv("FAKE_INPUT")]
    else:
        raw_input = sys.stdin.read()
        json_input = json.loads(raw_input)
        logger.debug(f"Input: {json_input}")

    if (
        json_input
        and "args" in json_input
        and "mode" in json_input["args"]
        and json_input["args"]["mode"] == "process_performers"
    ):
        process_performers()
    elif (
        json_input
        and "args" in json_input
        and "hookContext" in json_input["args"]
        and "type" in json_input["args"]["hookContext"]
        and json_input["args"]["hookContext"]["type"] == "Scene.Update.Post"
    ):
        stash_id = next(
            (
                sid["stash_id"]
                for sid in json_input["args"]["hookContext"]["input"]["stash_ids"]
                if sid.get("endpoint") == config.STASHDB_ENDPOINT
            ),
            None,
        )
        process_updated_scene(stash_id)
    else:
        logger.error(f"Invalid input: {json_input}")


if __name__ == "__main__":
    compare_performer_scenes()
