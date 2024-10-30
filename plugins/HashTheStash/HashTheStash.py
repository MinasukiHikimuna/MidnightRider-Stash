import json
import os
import sys
import hashlib
import stashapi.log as logger
from stashapi.stashapp import StashInterface
try:
    import xxhash
except ImportError:
    logger.error("xxhash is not installed. Please install it using 'pip install xxhash'.")
    has_xxhash = False

def hash_file(file_path, add_xxhash=False, add_sha256=False, add_sha1=False):
    fingerprints = []
    if has_xxhash:
        xxhash_hasher = xxhash.xxh64()
    sha256_hasher = hashlib.sha256()
    sha1_hasher = hashlib.sha1()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            if add_xxhash and has_xxhash:
                xxhash_hasher.update(chunk)
            if add_sha256:
                sha256_hasher.update(chunk)
            if add_sha1:
                sha1_hasher.update(chunk)

    if add_xxhash and has_xxhash:
        fingerprints.append({"type": "xxhash", "value": xxhash_hasher.hexdigest()})
    if add_sha256:
        fingerprints.append({"type": "sha256", "value": sha256_hasher.hexdigest()})
    if add_sha1:
        fingerprints.append({"type": "sha1", "value": sha1_hasher.hexdigest()})
    return fingerprints

def test_hash_file(stash, file, use_xxhash, use_sha256, use_sha1):
    file_path = file["path"]
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return

    add_xxhash = use_xxhash and ("fingerprints" not in file or not any(
        fp["type"] == "xxhash" for fp in file["fingerprints"]
    ))
    add_sha256 = use_sha256 and ("fingerprints" not in file or not any(
        fp["type"] == "sha256" for fp in file["fingerprints"]
    ))
    add_sha1 = use_sha1 and ("fingerprints" not in file or not any(
        fp["type"] == "sha1" for fp in file["fingerprints"]
    ))

    if not add_xxhash and not add_sha256 and not add_sha1:
        # if no fingerprints to add, just skip
        return

    fingerprints_to_set = hash_file(file_path, add_xxhash, add_sha256, add_sha1)

    if fingerprints_to_set:
        logger.info(
            f"File: {file_path}, new fingerprints: {fingerprints_to_set}"
        )
        stash.file_set_fingerprints(file["id"], fingerprints_to_set)

# common queries
fragment = """
    id
    files {
        id path
        fingerprints {
            type
        }
    }
"""

def hash_scenes(stash, use_xxhash, use_sha256, use_sha1):
    scenes_result = stash.find_scenes(fragment=fragment, get_count=True)
    scenes_count = scenes_result[0]
    scenes = scenes_result[1]

    processed = 0

    for scene in scenes:
        for file in scene["files"]:
            test_hash_file(stash, file, use_xxhash, use_sha256, use_sha1)
            processed += 1
            logger.progress(processed/scenes_count)
    logger.info(f"Processed a total of {scenes_count} scenes.")

def hash_galleries(stash, use_xxhash, use_sha256, use_sha1):
    galleries_result = stash.find_galleries(fragment=fragment, get_count=True)
    galleries_count = galleries_result[0]
    galleries = galleries_result[1]

    processed = 0

    for gallery in galleries:
        for file in gallery["files"]:
            test_hash_file(stash, file, use_xxhash, use_sha256, use_sha1)
            processed += 1
            logger.progress(processed/galleries_count)
    logger.info(f"Processed a total of {galleries_count} galleries.")

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

# Example usage
if __name__ == "__main__":
    json_input = get_json_input()
    logger.debug(f"Input: {json_input}")

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

    if not has_xxhash and use_xxhash:
        logger.error("xxhash is requested but not installed. Please install it using 'pip install xxhash'.")
        sys.exit(1)

    use_hash_galleries = plugin_configuration.get("hash_galleries", False)
    use_hash_scenes = plugin_configuration.get("hash_scenes", False)

    if not use_hash_scenes and not use_hash_galleries:
        logger.error("Neither scenes nor galleries selected for hashing. Please select at least one.")
        sys.exit(1)

    if use_hash_scenes:
        hash_scenes(stash, use_xxhash, use_sha256, use_sha1)

    if use_hash_galleries:
        hash_galleries(stash, use_xxhash, use_sha256, use_sha1)
