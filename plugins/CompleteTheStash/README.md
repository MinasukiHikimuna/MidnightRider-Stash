# Complete The Stash

This plugin is designed to compare local performer scenes with those available on StashDB. Any missing scenes will be created in a separate, missing Stash instance.

This plugin will not add, modify or delete anything in your main Stash instance. This plugin will read which performers you have tagged to be included in the comparison, get a list of all scenes of those performers from StashDB and create these missing scenes in the separate, missing Stash instance. Now you can easily see from that separate instance which scenes you are missing and you can filter those by site or by tags.

Complete The Stash requires `stashapp-tools` to be installed:

```
pip install -U stashapp-tools
```

## History

This plugin was originally developed by Serechops but due to major overhaul it was split as a separate plugin.

You can find the original plugin here: https://github.com/Serechops/Serechops-Stash/tree/main/plugins/performerSceneCompare#performer-scene-compare

## Features

- Compare local performer scenes with StashDB.
- Automatically create missing scenes with studios, tags and descriptions in a separate, missing Stash instance for performers tagged with your configured tag (by default Completionist).
- Missing scenes can be excluded by tags e.g. for avoiding compilations.
- Missing scenes are automatically deleted from the missing Stash instance when you add those to your main Stash.

## Setting up a second (or a third) Stash instance

These instructions are for Windows users which the majority of the users probably are.

Quick start:

1. Open a PowerShell
2. `mkdir C:\Stash_Missing_StashDB`
3. `cd C:\Stash_Missing_StashDB`
4. `& stash-win.exe --config C:\Stash_Missing_StashDB\config.yml --port 9998`
5. Open http://localhost:9998
6. Complete first time set up
7. Set up credentials by setting username and password. This is required for setting up API key.
8. Create an API key which will be used in the Configuration section.

### Troubleshooting

```
&: The term 'stash-win.exe' is not recognized as a name of a cmdlet, function, script file, or executable program.
Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
```

Your stash-win.exe is somewhere that PowerShell cannot find it from. Please find it for example with Windows Explorer and copy the full path to it by right-clicking on stash-win.exe and clicking Copy Path. After that adjust the command to: `& C:\some\full\path\stash-win.exe --config C:\Stash_Missing_StashDB\config.yml --port 9998`

```
ERRO[2024-08-23 05:16:19] http server error: listen tcp 0.0.0.0:9999: bind: Only one usage of each socket address (protocol/network address/port) is normally permitted.
```

In this case your selected port was already being used. Choose another one such as 9997 and try again.

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

The script is designed to be executed as a plugin within Stash. The plugin has a task "Complete The Stash!" which reads through your tagged performers and creates scenes in your missing Stash instances. This will create, update and delete scenes in the missing Stash instances.

Optionally, you can enable hooks which will automatically remove missing scenes when they are added to your main Stash. However, due to the current plugin architecture, this will significantly slow down your Stash as each update of any scene will trigger a hook. Every run will take a few seconds. This can be especially problematic when doing batch changes for potentially thousands of scenes.

Hooks can be enabled in CompleteTheStash.yml by uncommenting the related lines.

## Requirements for development

Running the plugin from VS Code during development reads sensitive values from .env file. This requires `python-dotenv`.

```
pip install -U python-dotenv
```

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
