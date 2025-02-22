from .client import SpotifyClient, BASE_URL
import configparser
import os

def get_config():
    project_root = os.path.dirname(os.path.dirname(__file__))
    config_path = os.path.join(project_root, "config", "config.ini")

    config = configparser.ConfigParser()
    config.read(config_path)

    return {
        "client_id": config.get("API", "client_id"),
        "client_secret": config.get("API", "client_secret"),
        "user_id": config.get("API", "user_id")
    }

def clear_liked_songs():
    print("\nConnecting to Spotify...")
    config = get_config()
    client = SpotifyClient(
        config["client_id"],
        config["client_secret"],
        config["user_id"]
    )

    total_removed = 0

    while True:
        # Each time we request the first 50 tracks
        request_args = {
            "url": f"{BASE_URL}/me/tracks",
            "headers": client.headers,
            "params": {
                "limit": 50
            }
        }

        response = client.send_request("GET", request_args)
        tracks = response["items"]

        if not tracks:
            break

        # Get the IDs of the tracks
        track_ids = [track["track"]["id"] for track in tracks]

        # Delete the tracks
        delete_args = {
            "url": f"{BASE_URL}/me/tracks",
            "headers": client.headers,
            "json": {
                "ids": track_ids
            }
        }
        client.send_request("DELETE", delete_args)

        total_removed += len(track_ids)
        print(f"Removed {len(track_ids)} tracks... (Total: {total_removed})")

    print(f"\nAll tracks have been removed from Liked Songs! (Total removed: {total_removed})")

if __name__ == "__main__":
    try:
        input("This will remove ALL tracks from your Liked Songs. Press Enter to continue or Ctrl+C to cancel...")
        clear_liked_songs()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")