import atexit
import io
import os.path
import subprocess
import time
from dotenv import load_dotenv
import os
import json
import zipfile
import shutil

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.http import MediaFileUpload

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive"]

def getLatestLocalBackup(LOCAL_SERVER_DIR):

    if not os.path.exists(LOCAL_SERVER_DIR):
        return -1

    # Get all files in the directory
    files = os.listdir(LOCAL_SERVER_DIR)
    # Filter out all files that are not .zip
    files = [f for f in files if f.endswith(".zip")]
    # Sort the files by name
    files.sort()
    # Return the last file
    return getBackupIterationFromName(files[-1])

def getBackupIterationFromName(name):
    # Try to get number from name, else return -1
    try:
        return int(name.split(".")[0])
    except:
        return -1

def run_mc_server_as_subprocess(LOCAL_SERVER_DIR):
    start_cmd = ["java", "-Xmx6G", "-jar", "fabric-server-launch.jar", "nogui"]
    global server_process_global
    server_process_global = subprocess.Popen(start_cmd, cwd=LOCAL_SERVER_DIR, stdin=subprocess.PIPE)
    print("Minecraft server started.")

    # Print the pids
    print(f"Server PID: {server_process_global.pid}")
    print(f"Server Process Group ID: {os.getpgid(server_process_global.pid)}")
    
    #Print this script's PID
    print(f"Script PID: {os.getpid()}")
    print(f"Script Process Group ID: {os.getpgrp()}")

def stop_server():
    if server_process_global:
        print("Stopping minecraft server...")
        server_process_global.stdin.write('/stop\n'.encode())
        server_process_global.stdin.flush()
        server_process_global.wait()  # Wait for the server to finish
        print("Minecraft server stopped.")
    else:
        print("ERROR: Server process could not be found.")

def clear_zips(directory):
    for filename in os.listdir(directory):
        if filename.endswith(".zip"):
            file_path = os.path.join(directory, filename)
            try:
                os.unlink(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")

def clear_directory(directory):
    if not os.path.exists(directory):
        return
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path) and not file_path.endswith(".zip"):
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
            metadata_results[item["name"]]["id"] = item["id"]
        else:
            metadata_results[item["name"]] = item

    return metadata_results

def main():
    load_dotenv()


    creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)

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
        latest_backups_keys.remove("id")
        latest_backups_keys.sort()
        latest_backup = latest_backups_keys[-1]

        # Download the latest backup to LOCAL_SERVER_DIR
        latest_backup_id = latest_backups[latest_backup]["id"]
        latest_backup_name = latest_backups[latest_backup]["name"]

        # If the latest backup is already downloaded, skip this step
        if getLatestLocalBackup(LOCAL_SERVER_DIR) >= getBackupIterationFromName(latest_backup_name):
            print(f"Latest backup already downloaded: {latest_backup_name}")
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
        run_mc_server_as_subprocess(LOCAL_SERVER_DIR)
        atexit.register(stop_server)

        # Schedule backups while the server is running
        while server_process_global and server_process_global.poll() is None:
            time.sleep(int(BACKUP_INTERVAL))

            # Stop the server
            stop_server()

            # Get index of latest backup from name
            latest_backup_index = getLatestLocalBackup(LOCAL_SERVER_DIR)
            next_index = latest_backup_index + 1
            
            print(f"Creating backup #{next_index}")

            # Remove current zip
            clear_zips(LOCAL_SERVER_DIR)

            # Zip the contents of the server directory
            # shutil.make_archive(f"{LOCAL_SERVER_DIR}/{next_index}", "zip", LOCAL_SERVER_DIR)
            with zipfile.ZipFile(f"{LOCAL_SERVER_DIR}/{next_index}.zip", "w", compression=zipfile.ZIP_DEFLATED) as zip_ref:
                for root, _, files in os.walk(LOCAL_SERVER_DIR):
                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, LOCAL_SERVER_DIR)
                        if relative_path == f"{next_index}.zip":
                            continue  # Skip the zip file itself
                        zip_ref.write(file_path, relative_path)

            print(f"Zipped contents to {next_index}.zip")

            # Upload the zip file to the backups folder
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            file_metadata = {
                "name": f"{next_index}.zip",
                "parents": [metadata["backups"][SERVER_NAME]["id"]],
            }
            # Create a MediaFileUpload object and specify resumable=True
            media = MediaFileUpload(
                f"{LOCAL_SERVER_DIR}/{next_index}.zip", 
                mimetype="application/zip", 
                resumable=True
            )

            print("Uploading backup file...")
            request = service.files().create(body=file_metadata, media_body=media)

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Uploaded {int(status.progress() * 100)}%")
            print(f"Created backup file: {next_index}.zip %s!" % response.get("id"))
            latest_backup_name = f"{next_index}.zip"

            # Start the server
            run_mc_server_as_subprocess(LOCAL_SERVER_DIR)

        print("Server stopped. Exiting...")

    except HttpError as error:
        # TODO(developer) - Handle errors from drive API.
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()
