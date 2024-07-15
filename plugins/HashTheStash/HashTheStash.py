import json
import os
import sys
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


# Example usage
if __name__ == "__main__":
    raw_input = sys.stdin.read()
    json_input = json.loads(raw_input)

    stash = StashInterface(json_input["server_connection"])

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
                if "fingerprints" not in file or not any(
                    fp["type"] == "xxhash" for fp in file["fingerprints"]
                ):
                    file_path = file["path"]
                    if not os.path.exists(file_path):
                        logger.warning(f"File not found: {file_path}")
                        continue

                    xxhash_value = get_xxhash_of_file(file_path)
                    logger.info(f"File: {file_path}, xxhash: {xxhash_value}")

                    stash.file_set_fingerprints(
                        file["id"], [{"type": "xxhash", "value": xxhash_value}]
                    )

        page += 1

    logger.info(f"Processed a total of {total_scenes} scenes.")
