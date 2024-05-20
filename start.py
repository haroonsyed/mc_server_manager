import atexit
import io
import os.path
import subprocess
from dotenv import load_dotenv
import os
import json
import zipfile
import shutil

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive"]

def run_mc_server_as_subprocess():
    start_cmd = "java -Xmx6G -jar fabric-server-launch.jar nogui"
    return subprocess.Popen(start_cmd, shell=True)

def stop_server():
    global server_process
    if server_process:
        print("Stopping minecraft server...")
        server_process.stdin.write('/stop\n')
        server_process.stdin.flush()
        server_process.wait()  # Wait for the server to finish
        print("Minecraft server stopped.")

def clear_directory(directory):
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")


def download_file(
    service, file_id, destination_folder, destination_file_name="server.zip"
):
    try:
        request = service.files().get_media(fileId=file_id)
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}.")

        # The file is now in RAM, save to a file at desired path
        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)
        with open(f"{destination_folder}/{destination_file_name}", "wb") as f:
            full_path = os.path.abspath(f.name)
            print(f"Saving to {full_path}")
            f.write(file.getvalue())

    except HttpError as error:
        print(f"An error occurred: {error}")
        file = None


def build_directory_structure(service, folder_id, indent=""):
    metadata_results = {}

    # List all files and folders in the current folder
    results = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=1000,  # Fix max limit by deleting old files
        )
        .execute()
    )
    items = results.get("files", [])

    for item in items:
        # If the item is a folder, recursively print its contents
        if item["mimeType"] == "application/vnd.google-apps.folder":
            metadata_results[item["name"]] = build_directory_structure(
                service, item["id"], indent + "  "
            )
        else:
            metadata_results[item["name"]] = item

    return metadata_results


def print_directory_structure(service, folder_id, indent=""):
    # List all files and folders in the current folder
    results = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents",
            fields="nextPageToken, files(id, name, mimeType)",
        )
        .execute()
    )
    items = results.get("files", [])

    for item in items:
        print(f"{indent}{item['name']}")

        # If the item is a folder, recursively print its contents
        if item["mimeType"] == "application/vnd.google-apps.folder":
            print_directory_structure(service, item["id"], indent + "  ")


def main():

    load_dotenv()

    """Shows basic usage of the Drive v3 API.
  Prints the names and ids of the first 10 files the user has access to.
  """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        # Get the environment variables
        SERVER_NAME = os.getenv("SERVER_NAME")
        BACKUP_INTERVAL = os.getenv("BACKUP_INTERVAL")
        ROOT_FOLDER = os.getenv("ROOT_FOLDER")
        LOCAL_SERVER_DIR = os.getenv("LOCAL_SERVER_DIR")
        print(f"Server Name: {SERVER_NAME}")
        print(f"Backup Interval: {BACKUP_INTERVAL}")

        service = build("drive", "v3", credentials=creds)

        # Get shared folder id by searching for PROD_MC_SERVER
        results = (
            service.files()
            .list(
                q=f"name='{ROOT_FOLDER}' and mimeType='application/vnd.google-apps.folder' and sharedWithMe",
                fields="files(id)",
            )
            .execute()
        )
        root_folder_id = results.get("files", [])[0]["id"]

        metadata = build_directory_structure(service, root_folder_id)
        json_metadata = json.dumps(metadata, indent=4)
        print(json_metadata)

        latest_backups = metadata["backups"][SERVER_NAME]
        # Each backup is 0.zip, 1.zip, 2.zip, etc.
        # Get all keys and sort them
        latest_backups_keys = list(latest_backups.keys())
        latest_backups_keys.sort()
        latest_backup = latest_backups_keys[-1]

        # Download the latest backup to LOCAL_SERVER_DIR
        latest_backup_id = latest_backups[latest_backup]["id"]
        latest_backup_name = latest_backups[latest_backup]["name"]

        # If the latest backup is already downloaded, skip this step
        if os.path.exists(f"{LOCAL_SERVER_DIR}/{latest_backup_name}"):
            print(f"Latest backup already downloaded: {latest_backup_name}")
            return
        else:
            clear_directory(LOCAL_SERVER_DIR)
            download_file(
                service, latest_backup_id, LOCAL_SERVER_DIR, latest_backup_name
            )

            # Unzip contents directly inside LOCAL_SERVER_DIR
            with zipfile.ZipFile(
                f"{LOCAL_SERVER_DIR}/{latest_backup_name}", "r"
            ) as zip_ref:
                zip_ref.extractall(LOCAL_SERVER_DIR)

        # Start the server
        server_process = run_mc_server_as_subprocess()
        atexit.register(stop_server)

        # Schedule backups

    except HttpError as error:
        # TODO(developer) - Handle errors from drive API.
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()
