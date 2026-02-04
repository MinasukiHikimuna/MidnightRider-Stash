import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import stashapi.log as logger
from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashCompleter import StashCompleter
from StashDbClient import StashDbClient
from TpdbClient import TpdbClient


STASHDB_ENDPOINT = os.environ.get("STASHDB_ENDPOINT", "https://stashdb.org/graphql")
TPDB_ENDPOINT = "https://theporndb.net/graphql"


@dataclass
class MissingSceneSource:
    stashapp_address: str
    stashapp_api_key: str
    stashbox_endpoint: str


@dataclass
class CompleteTheStashConfiguration:
    performer_tags: str
    scene_exclude_tags: str
    stashdb_scene_source: MissingSceneSource
    tpdb_scene_source: MissingSceneSource
    enable_scene_hooks: bool


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
            "Local and missing Stash instances have the same API key which indicates both local and missing "
            "Stash instances are the same. Please create a different instance for missing Stash."
        )


def get_json_input():
    if os.getenv("ENABLE_DEV_MODE"):
        import dotenv  # noqa: PLC0415
        dotenv.load_dotenv()

        fake_input = os.getenv("FAKE_INPUT")
        if not fake_input:
            raise ValueError("FAKE_INPUT environment variable is not set.")
        return json.loads(fake_input)
    raw_input = sys.stdin.read()
    return json.loads(raw_input)


def get_matching_stashbox_config(
    local_configuration, missing_scene_source: MissingSceneSource
):
    stashbox_endpoint = missing_scene_source.stashbox_endpoint
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
            "No missing Stash instances are configured. No missing scenes can be sourced. "
            "Are you missing configuration?"
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

    performer_tags = [tag.strip() for tag in complete_the_stash_config.get("performerTags").split(",")]
    scene_exclude_tags = [tag.strip() for tag in complete_the_stash_config.get("sceneExcludeTags", "").split(",")]

    stash_db_configuration = None
    if complete_the_stash_config.get(
        "missingStashAddress"
    ) and complete_the_stash_config.get("missingStashApiKey"):
        stash_db_configuration = MissingSceneSource(
            stashapp_address=complete_the_stash_config.get("missingStashAddress"),
            stashapp_api_key=complete_the_stash_config.get("missingStashApiKey"),
            stashbox_endpoint=STASHDB_ENDPOINT,
        )

    tpdb_configuration = None
    if complete_the_stash_config.get(
        "missingStashTpdbAddress"
    ) and complete_the_stash_config.get("missingStashTpdbApiKey"):
        tpdb_configuration = MissingSceneSource(
            stashapp_address=complete_the_stash_config.get("missingStashTpdbAddress"),
            stashapp_api_key=complete_the_stash_config.get("missingStashTpdbApiKey"),
            stashbox_endpoint=TPDB_ENDPOINT,
        )

    return CompleteTheStashConfiguration(
        performer_tags=performer_tags,
        scene_exclude_tags=scene_exclude_tags,
        stashdb_scene_source=stash_db_configuration,
        tpdb_scene_source=tpdb_configuration,
        enable_scene_hooks=complete_the_stash_config.get("enableSceneHooks", False),
    )


def create_missing_stash_client(missing_scene_source: MissingSceneSource):
    scheme, host, port = parse_url(missing_scene_source.stashapp_address)
    return MissingStashClient(
        scheme,
        host,
        port,
        missing_scene_source.stashapp_api_key,
        missing_scene_source.stashbox_endpoint,
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

        endpoint = stash_completer.stashbox_client.endpoint
        logger.debug(f"Processing scene create type {event_type} for scene {scene_id} for endpoint {endpoint}.")
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
    if event_type in ["Scene.Create.Post", "Scene.Update.Post"] and not complete_the_stash_config.enable_scene_hooks:
        return

    # StashDB
    if complete_the_stash_config.stashdb_scene_source:
        missing_stash_client = create_missing_stash_client(
            complete_the_stash_config.stashdb_scene_source
        )
        missing_configuration = missing_stash_client.get_configuration()

        check_stash_instances_are_unique(local_configuration, missing_configuration)

        stashbox_config = get_matching_stashbox_config(
            local_configuration, complete_the_stash_config.stashdb_scene_source
        )
        stashbox_client = StashDbClient(
            stashbox_config["endpoint"],
            stashbox_config["api_key"],
        )

        config = {
            "performerTags": complete_the_stash_config.performer_tags,
            "stashboxEndpoint": complete_the_stash_config.stashdb_scene_source.stashbox_endpoint,
            "sceneExcludeTags": complete_the_stash_config.scene_exclude_tags,
            "enableSceneHooks": complete_the_stash_config.enable_scene_hooks,
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
    if complete_the_stash_config.tpdb_scene_source:
        missing_stash_client = create_missing_stash_client(
            complete_the_stash_config.tpdb_scene_source
        )
        missing_configuration = missing_stash_client.get_configuration()

        check_stash_instances_are_unique(local_configuration, missing_configuration)

        stashbox_config = get_matching_stashbox_config(
            local_configuration, complete_the_stash_config.tpdb_scene_source
        )
        stashbox_client = TpdbClient(
            stashbox_config["endpoint"],
            stashbox_config["api_key"],
        )

        config = {
            "performerTags": complete_the_stash_config.performer_tags,
            "stashboxEndpoint": complete_the_stash_config.tpdb_scene_source.stashbox_endpoint,
            "sceneExcludeTags": complete_the_stash_config.scene_exclude_tags,
            "enableSceneHooks": complete_the_stash_config.enable_scene_hooks,
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
    script_dir = str(Path(__file__).resolve().parent)
    sys.path.append(script_dir)

    execute()
