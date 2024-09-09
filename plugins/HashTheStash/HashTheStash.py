import json
import os
import sys
import hashlib
import xxhash
import stashapi.log as logger
from stashapi.stashapp import StashInterface


def get_xxhash_of_file(file_path):
    # Create an xxhash object
    hasher = xxhash.xxh64()

    # Open the file in binary mode
    with open(file_path, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)

    # Return the hexadecimal representation of the hash
    return hasher.hexdigest()


def get_sha256_of_file(file_path):
    # Create a SHA-256 hash object
    hasher = hashlib.sha256()

    # Open the file in binary mode
    with open(file_path, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)

    # Return the hexadecimal representation of the hash
    return hasher.hexdigest()


def get_sha1_of_file(file_path):
    # Create a SHA-1 hash object
    hasher = hashlib.sha1()

    # Open the file in binary mode
    with open(file_path, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)

    # Return the hexadecimal representation of the hash
    return hasher.hexdigest()


# Example usage
if __name__ == "__main__":
    raw_input = sys.stdin.read()
    json_input = json.loads(raw_input)

    stash = StashInterface(json_input["server_connection"])
    configuration = stash.get_configuration()
    plugin_configuration = configuration["plugins"]["HashTheStash"]

    # Get hash settings
    use_xxhash = plugin_configuration.get("xxhash", False)
    use_sha256 = plugin_configuration.get("sha256", False)
    use_sha1 = plugin_configuration.get("sha1", False)

    if not use_xxhash and not use_sha256 and not use_sha1:
        logger.error("No hash type selected. Please select at least one hash type.")
        sys.exit(1)

    fragment = """
            id
            files {
                id
                path
                fingerprints {
                    type 
                    value
                }
            }
    """

    per_page = 25
    page = 1
    total_scenes = 0

    while True:
        scenes_result = stash.find_scenes(
            {}, {"per_page": per_page, "page": page}, "", fragment, get_count=True
        )
        scenes_count = scenes_result[0]
        scenes = scenes_result[1]

        if not scenes:
            break

        total_scenes += len(scenes)

        for scene in scenes:
            for file in scene["files"]:
                file_path = file["path"]
                if not os.path.exists(file_path):
                    logger.warning(f"File not found: {file_path}")
                    continue

                fingerprints_to_set = []

                if use_xxhash and ("fingerprints" not in file or not any(
                    fp["type"] == "xxhash" for fp in file["fingerprints"]
                )):
                    xxhash_value = get_xxhash_of_file(file_path)
                    fingerprints_to_set.append(
                        {"type": "xxhash", "value": xxhash_value}
                    )

                if use_sha256 and ("fingerprints" not in file or not any(
                    fp["type"] == "sha256" for fp in file["fingerprints"]
                )):
                    sha256_value = get_sha256_of_file(file_path)
                    fingerprints_to_set.append(
                        {"type": "sha256", "value": sha256_value}
                    )

                if use_sha1 and ("fingerprints" not in file or not any(
                    fp["type"] == "sha1" for fp in file["fingerprints"]
                )):
                    sha1_value = get_sha1_of_file(file_path)
                    fingerprints_to_set.append(
                        {"type": "sha1", "value": sha1_value}
                    )

                if fingerprints_to_set:
                    logger.info(
                        f"File: {file_path}, new fingerprints: {fingerprints_to_set}"
                    )
                    stash.file_set_fingerprints(file["id"], fingerprints_to_set)

        page += 1

    logger.info(f"Processed a total of {total_scenes} scenes.")
