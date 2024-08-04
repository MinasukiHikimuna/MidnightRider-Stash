import pandas as pd
import stashapi.log as log
from stashapi.stashapp import StashInterface
from dotenv import load_dotenv
import os

# Load the .env file
load_dotenv()

# Get the API key
scheme = os.getenv("STASHAPP_SCHEME")
host = os.getenv("STASHAPP_HOST")
port = os.getenv("STASHAPP_PORT")
api_key = os.getenv("STASHAPP_API_KEY")


def get_stashapp_client():
    stash = StashInterface(
        {
            "scheme": scheme,
            "host": host,
            "port": port,
            "logger": log,
            "ApiKey": api_key,
        }
    )
    return stash
