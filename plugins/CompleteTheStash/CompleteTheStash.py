import json
import os
import sys
from urllib.parse import urlparse
import dotenv

import stashapi.log as logger
from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashDbClient import StashDbClient
from StashCompleter import StashCompleter

dotenv.load_dotenv()


def parse_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme
    host = parsed_url.hostname
    port = parsed_url.port or (443 if scheme == "https" else 80)
    return scheme, host, port


def check_stash_instances_are_unique(local_configuration, missing_configuration):
    local_api_key = local_configuration.get("general", {}).get("apiKey")
    missing_api_key = missing_configuration.get("general", {}).get("apiKey")
    if local_api_key == missing_api_key:
        raise ValueError(
            "Local and missing Stash instances have the same API key which indicates both local and missing Stash instances are the same. "
            "Please create a different instance for missing Stash."
        )


def get_json_input():
    if os.getenv("FAKE_INPUT"):
        from fakeInput import fake_input

        return fake_input[os.getenv("FAKE_INPUT")]
    else:
        raw_input = sys.stdin.read()
        return json.loads(raw_input)


def get_stashdb_stash_box(local_configuration, config):
    stash_boxes = local_configuration.get("general", {}).get("stashBoxes")
    if not stash_boxes:
        raise ValueError("No stash boxes are configured.")
    stashdb_stash_box = next(
        (
            box
            for box in stash_boxes
            if box.get("endpoint") == config.get("stashboxEndpoint")
        ),
        None,
    )
    if not stashdb_stash_box:
        raise ValueError("StashDB stash box is not configured.")
    return stashdb_stash_box


def create_stashdb_client(local_configuration, stashdb_stash_box):
    scene_exclude_tags = (
        local_configuration.get("plugins", {})
        .get("CompleteTheStash", {})
        .get("sceneExcludeTags", "")
        .split(",")
    )
    return StashDbClient(
        stashdb_stash_box["endpoint"],
        stashdb_stash_box["api_key"],
        scene_exclude_tags,
    )


def get_complete_the_stash_config(local_configuration):
    plugins_configuration = local_configuration.get("plugins", {})
    complete_the_stash_config = plugins_configuration.get("CompleteTheStash")
    if not complete_the_stash_config:
        raise ValueError("CompleteTheStash plugin is not configured.")

    if not complete_the_stash_config.get("missingStashAddress"):
        raise ValueError(
            "Missing Stash URL is not configured. Please set in Plugins configuration."
        )
    if not complete_the_stash_config.get("missingStashApiKey"):
        raise ValueError(
            "Missing Stash API key is not configured. Please set in Plugins configuration."
        )
    if not complete_the_stash_config.get("performerTags"):
        raise ValueError(
            "Performer tags are not configured. Please set in Plugins configuration."
        )

    return complete_the_stash_config


def create_missing_stash_client(complete_the_stash_config, config):
    missing_stash_url = complete_the_stash_config.get("missingStashAddress")
    if not missing_stash_url:
        raise ValueError("Missing Stash URL is not configured.")
    missing_stash_api_key = complete_the_stash_config.get("missingStashApiKey")
    if not missing_stash_api_key:
        raise ValueError("Missing Stash API key is not configured.")
    scheme, host, port = parse_url(missing_stash_url)
    return MissingStashClient(
        scheme,
        host,
        port,
        missing_stash_api_key,
        config.get("stashboxEndpoint"),
        logger,
    )


def process_input(json_input, stash_completer: StashCompleter, config):
    logger.debug(f"Processing input: {json_input}")
    event_type = json_input.get("args", {}).get("hookContext", {}).get("type")
    if json_input.get("args", {}).get("mode") == "process_performers":
        stash_completer.process_performers()
    elif event_type == "Scene.Create.Post":
        try:
            scene_id = json_input.get("args", {}).get("hookContext", {}).get("id")
        except AttributeError:
            scene_id = None

        if scene_id is None:
            logger.debug(
                f"Scene ID is not provided in the input for type {event_type}. Skipping."
            )
            return

        logger.debug(f"Processing scene create type {event_type} for scene {scene_id}.")
        stash_completer.process_scene_by_id(scene_id)
    elif event_type == "Scene.Update.Post":
        try:
            stash_ids = (
                json_input.get("args", {})
                .get("hookContext", {})
                .get("input", {})
                .get("stash_ids", [])
            )
        except AttributeError:
            stash_ids = []

        stash_id = next(
            (sid.get("stash_id") for sid in stash_ids),
            None,
        )
        if (stash_id is None) or (stash_id == ""):
            logger.debug(
                f"Stash ID is not provided in the input for type {event_type}. Skipping."
            )
            return

        logger.debug(f"Processing scene update type {event_type} for scene {stash_id}.")
        stash_completer.process_scene_by_stashbox_id(stash_id)
    else:
        logger.error(f"Invalid input: {json_input}")


def execute():
    json_input = get_json_input()
    logger.debug(f"Input: {json_input}")

    if os.getenv("FAKE_INPUT"):
        local_stash_client = LocalStashClient.create_with_api_key(
            os.getenv("LOCAL_STASH_SCHEME"),
            os.getenv("LOCAL_STASH_HOST"),
            os.getenv("LOCAL_STASH_PORT"),
            os.getenv("LOCAL_STASH_API_KEY"),
            logger,
        )
    else:
        local_stash_client = LocalStashClient(json_input["server_connection"], logger)
    local_configuration = local_stash_client.get_configuration()
    logger.debug(f"Local configuration: {local_configuration}")

    performer_tags = (
        local_configuration.get("plugins", {})
        .get("CompleteTheStash", {})
        .get("performerTags")
    ).split(",")
    config = {
        "performerTags": performer_tags,
        "stashboxEndpoint": "https://stashdb.org/graphql",
    }

    complete_the_stash_config = get_complete_the_stash_config(local_configuration)

    missing_stash_client = create_missing_stash_client(
        complete_the_stash_config, config
    )
    missing_configuration = missing_stash_client.get_configuration()

    check_stash_instances_are_unique(local_configuration, missing_configuration)

    stashdb_stash_box = get_stashdb_stash_box(local_configuration, config)
    stashdb_client = create_stashdb_client(local_configuration, stashdb_stash_box)

    stash_completer = StashCompleter(
        config,
        logger,
        stashdb_client,
        local_stash_client,
        missing_stash_client,
    )
    process_input(json_input, stash_completer, config)


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(script_dir)

    execute()
