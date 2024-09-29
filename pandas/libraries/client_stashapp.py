import pandas as pd
import stashapi.log as log
from stashapi.stashapp import StashInterface
from dotenv import load_dotenv
import os

# Load the .env file
load_dotenv()

def get_stashapp_client(prefix=""):
    # Use the provided prefix to get environment variables
    scheme = os.getenv(f"{prefix}STASHAPP_SCHEME")
    host = os.getenv(f"{prefix}STASHAPP_HOST")
    port = os.getenv(f"{prefix}STASHAPP_PORT")
    api_key = os.getenv(f"{prefix}STASHAPP_API_KEY")

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