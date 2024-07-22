import json
import os
import sys
from urllib.parse import urlparse

import stashapi.log as logger
from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashDbClient import StashDbClient
from StashCompleter import StashCompleter


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


def process_input(json_input, stash_completer, config):
    if json_input.get("args", {}).get("mode") == "process_performers":
        stash_completer.process_performers()
    elif (
        json_input.get("args", {}).get("hookContext", {}).get("type")
        == "Scene.Update.Post"
    ):
        stash_id = next(
            (
                sid["stash_id"]
                for sid in json_input["args"]["hookContext"]["input"]["stash_ids"]
                if sid.get("endpoint") == config.get("stashboxEndpoint")
            ),
            None,
        )
        stash_completer.process_updated_scene(stash_id)
    else:
        logger.error(f"Invalid input: {json_input}")


def execute():
    json_input = get_json_input()
    logger.debug(f"Input: {json_input}")

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
