# Complete The Stash

This plugin is designed to compare local performer scenes with those available on StashDB. Any missing scenes will be created in a separate, missing Stash instance.

This plugin will not add, modify or delete anything in your main Stash instance. This plugin will read which performers you have tagged to be included in the comparison, get a list of all scenes of those performers from StashDB and create these missing scenes in the separate, missing Stash instance. Now you can easily see from that separate instance which scenes you are missing and you can filter those by site or by tags.

## History

This plugin was originally developed by Serechops but due to major overhaul it was split as a separate plugin.

You can find the original plugin here: https://github.com/Serechops/Serechops-Stash/tree/main/plugins/performerSceneCompare#performer-scene-compare

## Features

- Compare local performer scenes with StashDB.
- Automatically create missing scenes with studios, tags and descriptions in a separate, missing Stash instance for performers tagged with your configured tag (by default Completionist).
- Missing scenes can be excluded by tags e.g. for avoiding compilations.
- Missing scenes are automatically deleted from the missing Stash instance when you add those to your main Stash.

## Configuration

All configuration is done in Plugins settings in your primary Stash.

Mandatory configuration values:

- Missing Stash address
  - URL of the Stash instance where missing scenes are created.
- Missing Stash API key
  - API key of the Stash instance where missing scenes are created.
- Include performers with tags
  - Tags of the performers selected for processing. Separate multiple tags with commas.

Optional configuration values:

- Exclude scenes with tags
  - Tags of the scenes to exclude from processing, e.g. Compilation. Separate multiple tags with commas.

## Usage

The script is designed to be executed as a plugin within Stash. It is triggered by:

- Executing "Process performers" task manually. This will create, update and possibly delete missing scenes.
- Local scene being updated. If a previously missing scene is now found in local Stash, it is deleted from missing Stash.

The separate task for longer running processing is critical for good user experience. For example if performer processing was triggered when a performer is tagged with Completionist, local Stash UI would look like being stuck until all, possibly thousands of scenes for that performer would have been processed.

## Requirements for development

`pip install stashapp-tools`

For development Python's pytest is used. You need to install it:

```
pip install -U pytest pytest-mock
```

You can tests like:

```
pytest
```

To run from Visual Studio Code with debugger

- with your actual local Stash, use launch.json.
- with E2E tests, debug E2E tests from Testing tab.

Both utilize .env file.

```
# For running with your actual local stash, following are required.
LOCAL_STASH_SCHEME=   #
LOCAL_STASH_HOST=
LOCAL_STASH_PORT=
LOCAL_STASH_API_KEY=

# For E2E tests, following are required.
STASH_BIN=            # Path to Stash binary
STASHDB_API_KEY=      # API key to StashDB, needed for E2E tests
TPDB_API_KEY=         # API key to TPDB, needed for E2E tests
```
