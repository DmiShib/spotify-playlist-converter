from json import dumps
from typing import List, Tuple, Dict, Union, Any
import base64
import requests
from requests.exceptions import RequestException, HTTPError
from urllib.parse import urlencode
import webbrowser
import http.server
import socketserver
import threading
import random
import string
import sys


# Base URL для API endpoints
BASE_URL = "https://api.spotify.com/v1"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

SEARCH_URL = f"{BASE_URL}/search"  # GET https://api.spotify.com/v1/search
CONTAINS_URL = f"{BASE_URL}/me/tracks/contains"  # GET https://api.spotify.com/v1/me/tracks/contains
PLAYLIST_URL = f"{BASE_URL}/users/{{user_id}}/playlists"  # POST https://api.spotify.com/v1/users/{user_id}/playlists
ADD_TRACK_URL = f"{BASE_URL}/playlists/{{playlist_id}}/tracks"  # POST https://api.spotify.com/v1/playlists/{playlist_id}/tracks
LIKED_SONGS_URL = f"{BASE_URL}/me/tracks"  # PUT https://api.spotify.com/v1/me/tracks

def print_progress_bar(current: int, total: int, prefix: str = '', suffix: str = '', length: int = 50) -> None:
    """Displays the progress bar in the console"""
    filled_length = int(length * current / total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {current}/{total} {suffix}', end='', flush=True)

class SpotifyAuthHandler(http.server.SimpleHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        if '/callback' in self.path and 'code=' in self.path:
            SpotifyAuthHandler.auth_code = self.path.split('code=')[1].split('&')[0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authorization successful! You can close this window.")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

class SpotifyClient:
    """Client makes requests to the Spotify API to create a playlist."""

    def __init__(self, client_id: str, client_secret: str, user_id: str, enable_logs: bool = False, add_to_liked: bool = False):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self.enable_logs = enable_logs
        self.add_to_liked = add_to_liked
        self.access_token = self._get_access_token()
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        self._validate_token()

    def log(self, message: str) -> None:
        """Outputs debugging information if logs are enabled"""
        if self.enable_logs:
            print(message)

    def _get_access_token(self) -> str:
        """Gets access token using Authorization Code Flow"""
        # Generate a random state
        state = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))

        # Parameters for authorization
        auth_params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': 'http://localhost:8888/callback',
            'state': state,
            'scope': ' '.join([
                'playlist-modify-public',
                'playlist-modify-private',
                'user-library-read',
                'user-library-modify',
                'user-read-private',
                'user-read-email'
            ])
        }

        # Open the browser for authorization
        auth_url = f"{AUTH_URL}?{urlencode(auth_params)}"
        webbrowser.open(auth_url)

        # Start the local server to get the code
        with socketserver.TCPServer(('', 8888), SpotifyAuthHandler) as httpd:
            httpd.handle_request()

        if not SpotifyAuthHandler.auth_code:
            raise Exception("Failed to get authorization code")

        # Get tokens using the received code
        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        token_data = {
            'grant_type': 'authorization_code',
            'code': SpotifyAuthHandler.auth_code,
            'redirect_uri': 'http://localhost:8888/callback'
        }

        response = requests.post(
            TOKEN_URL,
            data=token_data,
            headers={
                'Authorization': f'Basic {auth_header}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        )

        if response.status_code != 200:
            raise Exception(f"Failed to get access token: {response.text}")

        return response.json()['access_token']

    def send_request(self, method: str, request_args: Dict) -> Any:
        """Sends a request to an API with logging support"""
        try:
            response = requests.request(method, **request_args)

            self.log(f"\nRequest URL: {request_args['url']}")
            self.log(f"Request Method: {method}")
            self.log(f"Request Headers: {request_args['headers']}")

            if 'params' in request_args:
                self.log(f"Request Params: {request_args['params']}")
            if 'data' in request_args:
                self.log(f"Request Data: {request_args['data']}")

            self.log(f"Response Status: {response.status_code}")
            self.log(f"Response Body: {response.text}\n")

            response.raise_for_status()
            # Возвращаем JSON только если есть содержимое
            return response.json() if response.text else None
        except HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
            print(f"Response content: {response.text}")
            raise
        except RequestException as e:
            print(f"Error making request: {e}")
            raise

    def _validate_token(self):
        """Checks the validity of the access token"""
        try:
            request_args = {
                "url": f"{BASE_URL}/me",
                "headers": self.headers
            }
            self.send_request("GET", request_args)
        except HTTPError as e:
            if e.response.status_code == 401:
                raise Exception("Invalid or expired access token. Please get a new token from Spotify.") from e
            raise

    def find_track_ids(self, track: str, artist: str) -> List[str]:
        query = f"{track} {artist}"
        request_args = {
            "url": SEARCH_URL,
            "headers": self.headers,
            "params": {
                "q": query,
                "type": "track",
                "limit": 10
            }
        }
        try:
            response_json = self.send_request("GET", request_args)
            tracks_found = response_json["tracks"]["items"]
            self.log(f"\nFound {len(tracks_found)} tracks for query: {query}")

            sorted_tracks = []
            other_tracks = []
            search_track = track.lower()

            for track_item in tracks_found:
                track_name = track_item['name'].lower()
                if search_track == track_name:
                    self.log(f"Exact match found: {track_item['name']} by {', '.join(a['name'] for a in track_item['artists'])}")
                    sorted_tracks.append(track_item)
                else:
                    other_tracks.append(track_item)
                    self.log(f"Other match: {track_item['name']} by {', '.join(a['name'] for a in track_item['artists'])}")

            all_tracks = sorted_tracks + other_tracks

            if sorted_tracks:
                self.log("\nUsing exact match as priority")
            elif other_tracks:
                self.log("\nNo exact matches found, using best available match")
            else:
                self.log("\nNo matches found")

            return [result["id"] for result in all_tracks]
        except Exception as e:
            print(f"Error searching for track '{track}' by '{artist}': {e}")
            return []

    def find_saved_track(self, track_ids: List[str]) -> Union[str, None]:
        # Check that we have no more than 50 tracks (API limitation)
        if len(track_ids) > 50:
            track_ids = track_ids[:50]

        request_args = {
            "url": CONTAINS_URL,
            "headers": self.headers,
            "params": {"ids": ",".join(track_ids)}
        }
        response_json = self.send_request("GET", request_args)
        return first_saved(list(zip(track_ids, response_json)))

    def get_track_id(self, track: str, artist: str) -> Union[str, None]:
        track_results = self.find_track_ids(track, artist)
        if not track_results:
            return None
        saved_track = self.find_saved_track(track_results)
        if not saved_track:
            return track_results[0]
        return saved_track

    def create_playlist(self, name: str) -> str:
        request_args = {
            "url": PLAYLIST_URL.format(user_id=self.user_id),
            "headers": self.headers,
            "data": dumps({
                "name": name,
                "public": False,  # Create a private playlist by default
                "description": "Created by Playlist Converter"
            })
        }
        response_json = self.send_request("POST", request_args)
        return response_json["id"]

    def add_playlist_tracks(self, pid: str, track_uris: List[str]) -> None:
        request_args = {
            "url": ADD_TRACK_URL.format(playlist_id=pid),
            "headers": self.headers
        }

        total_tracks = len(track_uris)

        # Adding tracks one at a time
        for i, track_uri in enumerate(track_uris, 1):
            try:
                request_args["data"] = dumps({
                    "uris": [track_uri]  # Pass one track
                })
                self.send_request("POST", request_args)

                if not self.enable_logs:
                    print_progress_bar(i, total_tracks, prefix='Adding tracks:', suffix='Complete')

            except Exception as e:
                print(f"Error adding track {track_uri} to playlist: {e}")
                continue

    def add_to_liked_songs(self, track_ids: List[str]) -> None:
        """Добавляет треки в Liked Songs"""
        request_args = {
            "url": LIKED_SONGS_URL,
            "headers": self.headers,
            "json": {  # Use json instead of data
                "ids": track_ids
            }
        }
        self.send_request("PUT", request_args)

    def make_playlist_with_tracks(
            self,
            playlist_name: str,
            tracks_with_artist: List[Tuple[str, str]]
        ) -> None:
        total_tracks = len(tracks_with_artist)
        found_tracks = 0

        if not self.add_to_liked:
            if self.enable_logs:
                print(f"\nProcessing playlist: {playlist_name}")
                print("Searching for tracks...")
            else:
                print(f"\nCreating playlist: {playlist_name}")

            playlist_id = self.create_playlist(playlist_name)
            self.log("Playlist created, adding tracks as they are found...")
        else:
            print("\nSearching and adding tracks to Liked Songs...")

        for i, pair in enumerate(reversed(tracks_with_artist), 1):
            try:
                track_id = self.get_track_id(*pair)
                if track_id:
                    if self.add_to_liked:
                        # Add to Liked Songs
                        self.add_to_liked_songs([track_id])
                    else:
                        # Add to playlist
                        track_uri = f"spotify:track:{track_id}"
                        request_args = {
                            "url": ADD_TRACK_URL.format(playlist_id=playlist_id),
                            "headers": self.headers,
                            "data": dumps({
                                "uris": [track_uri]
                            })
                        }
                        self.send_request("POST", request_args)
                    found_tracks += 1

                if not self.enable_logs:
                    print_progress_bar(i, total_tracks, prefix='Progress:', suffix='Complete')
            except Exception as e:
                print(f"Error processing track {pair}: {e}")
                continue

        if found_tracks > 0:
            if self.add_to_liked:
                print(f"\nSuccessfully added {found_tracks} tracks to Liked Songs!")
            else:
                print(f"\nPlaylist created successfully!")
        else:
            print("\nNo tracks were found to add")

def first_saved(tracks_saved: List[Tuple[str, bool]]) -> Union[str, None]:
    for tid, saved in tracks_saved:
        if saved:
            return tid
    return None
