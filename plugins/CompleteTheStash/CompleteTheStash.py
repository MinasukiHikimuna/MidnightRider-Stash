from dataclasses import dataclass
import json
import os
import sys
from urllib.parse import urlparse

import stashapi.log as logger
from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashCompleter import StashCompleter
from StashDbClient import StashDbClient
from TpdbClient import TpdbClient


@dataclass
class MissingSceneSource:
    stashappAddress: str
    stashappApiKey: str
    stashboxEndpoint: str


@dataclass
class CompleteTheStashConfiguration:
    performerTags: str
    sceneExcludeTags: str
    stashDbSceneSource: MissingSceneSource
    tpdbSceneSource: MissingSceneSource
    enableSceneHooks: bool


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
    if os.getenv("ENABLE_DEV_MODE"):
        import dotenv
        dotenv.load_dotenv()

        fake_input = os.getenv("FAKE_INPUT")
        if not fake_input:
            raise ValueError("FAKE_INPUT environment variable is not set.")
        return json.loads(fake_input)
    else:
        raw_input = sys.stdin.read()
        return json.loads(raw_input)


def get_matching_stashbox_config(
    local_configuration, missing_scene_source: MissingSceneSource
):
    stashbox_endpoint = missing_scene_source.stashboxEndpoint
    stash_boxes = local_configuration.get("general", {}).get("stashBoxes")
    if not stash_boxes:
        raise ValueError("No stash boxes are configured.")
    matching_stashbox = next(
        (box for box in stash_boxes if box.get("endpoint") == stashbox_endpoint),
        None,
    )
    if not matching_stashbox:
        raise ValueError(
            f"Stashbox is not configured for endpoint {stashbox_endpoint}."
        )
    return matching_stashbox


def get_complete_the_stash_config(local_configuration) -> CompleteTheStashConfiguration:
    plugins_configuration = local_configuration.get("plugins", {})
    complete_the_stash_config = plugins_configuration.get("CompleteTheStash")

    if not complete_the_stash_config:
        raise ValueError("CompleteTheStash plugin is not configured.")

    if not complete_the_stash_config.get("performerTags"):
        raise ValueError("Performer tags are not configured.")

    if (
        not complete_the_stash_config.get("missingStashAddress")
        and not complete_the_stash_config.get("missingStashApiKey")
        and not complete_the_stash_config.get("missingStashTpdbAddress")
        and not complete_the_stash_config.get("missingStashTpdbApiKey")
    ):
        raise ValueError(
            "No missing Stash instances are configured. No missing scenes can be sourced. Are you missing configuration?"
        )

    if complete_the_stash_config.get(
        "missingStashAddress"
    ) or complete_the_stash_config.get("missingStashApiKey"):
        if not complete_the_stash_config.get("missingStashAddress"):
            raise ValueError(
                "URL for missing Stash for StashDB scenes is not configured. Please set in Plugins configuration."
            )
        if not complete_the_stash_config.get("missingStashApiKey"):
            raise ValueError(
                "API Key for missing Stash for StashDB scenes is not configured. Please set in Plugins configuration."
            )

    if complete_the_stash_config.get(
        "missingStashTpdbAddress"
    ) or complete_the_stash_config.get("missingStashTpdbApiKey"):
        if not complete_the_stash_config.get("missingStashTpdbAddress"):
            raise ValueError(
                "URL for missing Stash for TPDB scenes is not configured. Please set in Plugins configuration."
            )
        if not complete_the_stash_config.get("missingStashTpdbApiKey"):
            raise ValueError(
                "API Key for missing Stash for TPDB scenes is not configured. Please set in Plugins configuration."
            )

    performer_tags = complete_the_stash_config.get("performerTags").split(",")
    scene_exclude_tags = complete_the_stash_config.get("sceneExcludeTags", "").split(
        ","
    )

    stash_db_configuration = None
    if complete_the_stash_config.get(
        "missingStashAddress"
    ) and complete_the_stash_config.get("missingStashApiKey"):
        stash_db_configuration = MissingSceneSource(
            stashappAddress=complete_the_stash_config.get("missingStashAddress"),
            stashappApiKey=complete_the_stash_config.get("missingStashApiKey"),
            stashboxEndpoint="https://stashdb.org/graphql",
        )

    tpdb_configuration = None
    if complete_the_stash_config.get(
        "missingStashTpdbAddress"
    ) and complete_the_stash_config.get("missingStashTpdbApiKey"):
        tpdb_configuration = MissingSceneSource(
            stashappAddress=complete_the_stash_config.get("missingStashTpdbAddress"),
            stashappApiKey=complete_the_stash_config.get("missingStashTpdbApiKey"),
            stashboxEndpoint="https://theporndb.net/graphql",
        )

    return CompleteTheStashConfiguration(
        performerTags=performer_tags,
        sceneExcludeTags=scene_exclude_tags,
        stashDbSceneSource=stash_db_configuration,
        tpdbSceneSource=tpdb_configuration,
        enableSceneHooks=complete_the_stash_config.get("enableSceneHooks", False),
    )


def create_missing_stash_client(missingSceneSource: MissingSceneSource):
    scheme, host, port = parse_url(missingSceneSource.stashappAddress)
    return MissingStashClient(
        scheme,
        host,
        port,
        missingSceneSource.stashappApiKey,
        missingSceneSource.stashboxEndpoint,
        logger,
    )


def process_input(json_input, stash_completer: StashCompleter):
    logger.debug(f"Processing input: {json_input}")
    event_type = json_input.get("args", {}).get("hookContext", {}).get("type")
    if json_input.get("args", {}).get("mode") == "process_performers":
        logger.info(f"Processing performers for endpoint {stash_completer.stashbox_client.endpoint}.")
        stash_completer.process_performers()
    elif event_type in ["Scene.Create.Post", "Scene.Update.Post"]:
        try:
            scene_id = json_input.get("args", {}).get("hookContext", {}).get("id")
        except AttributeError:
            scene_id = None

        if scene_id is None:
            logger.debug(
                f"Scene ID is not provided in the input for type {event_type}. Skipping."
            )
            return

        logger.debug(f"Processing scene create type {event_type} for scene {scene_id} for endpoint {stash_completer.stashbox_client.endpoint}.")
        stash_completer.process_scene_by_id(scene_id)
    else:
        logger.error(f"Invalid input: {json_input}")


def execute():
    json_input = get_json_input()
    logger.debug(f"Input: {json_input}")

    local_stash_client = LocalStashClient(json_input["server_connection"], logger)
    local_configuration = local_stash_client.get_configuration()
    logger.debug(f"Local configuration: {local_configuration}")

    complete_the_stash_config = get_complete_the_stash_config(local_configuration)

    # Stop processing as soon as possible to improve performance if scene hooks are disabled.
    event_type = json_input.get("args", {}).get("hookContext", {}).get("type")
    if event_type in ["Scene.Create.Post", "Scene.Update.Post"] and not complete_the_stash_config.enableSceneHooks:
        return

    # StashDB
    if complete_the_stash_config.stashDbSceneSource:
        missing_stash_client = create_missing_stash_client(
            complete_the_stash_config.stashDbSceneSource
        )
        missing_configuration = missing_stash_client.get_configuration()

        check_stash_instances_are_unique(local_configuration, missing_configuration)

        stashbox_config = get_matching_stashbox_config(
            local_configuration, complete_the_stash_config.stashDbSceneSource
        )
        stashbox_client = StashDbClient(
            stashbox_config["endpoint"],
            stashbox_config["api_key"],
        )

        config = {
            "performerTags": complete_the_stash_config.performerTags,
            "stashboxEndpoint": complete_the_stash_config.stashDbSceneSource.stashboxEndpoint,
            "sceneExcludeTags": complete_the_stash_config.sceneExcludeTags,
            "enableSceneHooks": complete_the_stash_config.enableSceneHooks,
        }
        stash_completer = StashCompleter(
            config,
            logger,
            stashbox_client,
            local_stash_client,
            missing_stash_client,
        )
        process_input(json_input, stash_completer)

    # TPDB
    if complete_the_stash_config.tpdbSceneSource:
        missing_stash_client = create_missing_stash_client(
            complete_the_stash_config.tpdbSceneSource
        )
        missing_configuration = missing_stash_client.get_configuration()

        check_stash_instances_are_unique(local_configuration, missing_configuration)

        stashbox_config = get_matching_stashbox_config(
            local_configuration, complete_the_stash_config.tpdbSceneSource
        )
        stashbox_client = TpdbClient(
            stashbox_config["endpoint"],
            stashbox_config["api_key"],
        )

        config = {
            "performerTags": complete_the_stash_config.performerTags,
            "stashboxEndpoint": complete_the_stash_config.tpdbSceneSource.stashboxEndpoint,
            "sceneExcludeTags": complete_the_stash_config.sceneExcludeTags,
            "enableSceneHooks": complete_the_stash_config.enableSceneHooks,
        }
        stash_completer = StashCompleter(
            config,
            logger,
            stashbox_client,
            local_stash_client,
            missing_stash_client,
        )
        process_input(json_input, stash_completer)


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(script_dir)

    execute()
