import json
import os
import sys
import stashapi.log as logger
from datetime import datetime

from LocalStashClient import LocalStashClient
from MissingStashClient import MissingStashClient
from StashDbClient import StashDbClient
from StashCompleter import StashCompleter


def check_stash_instances_are_unique(config):
    if (
        config.LOCAL_GQL_SCHEME == config.MISSING_GQL_SCHEME
        and config.LOCAL_GQL_HOST == config.MISSING_GQL_HOST
        and config.LOCAL_GQL_PORT == config.MISSING_GQL_PORT
    ):
        raise ValueError(
            "Local and missing Stash instances are the same. Please create a different instance for missing Stash."
        )


def check_performer_tags_are_configured(config):
    if not config.PERFORMER_TAGS:
        raise ValueError("No performer tags are configured.")


def check_config(config):
    check_stash_instances_are_unique(config)
    check_performer_tags_are_configured(config)


def compare_performer_scenes(config):
    check_config(config)

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
    stash_completer = StashCompleter(
        config, logger, stashdb_client, local_stash_client, missing_stash_client
    )

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
        stash_completer.process_performers()
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
        stash_completer.process_updated_scene(stash_id)
    else:
        logger.error(f"Invalid input: {json_input}")


if __name__ == "__main__":
    # Ensure the script can locate config.py
    script_dir = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(script_dir)

    import config  # Import the configuration

    try:
        compare_performer_scenes(config)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
