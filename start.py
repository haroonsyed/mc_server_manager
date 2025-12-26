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

load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive"]
CLOUD_ROOT_FOLDER = os.getenv("CLOUD_ROOT_FOLDER")
CLOUD_SERVER_NAME = os.getenv("CLOUD_SERVER_NAME")
LOCAL_SERVER_DIR = os.getenv("LOCAL_SERVER_DIR")
LOCAL_BACKUP_DIR = os.getenv("LOCAL_BACKUP_DIR")
LOCAL_BACKUP_INTERVAL = os.getenv("LOCAL_BACKUP_INTERVAL")
ONLINE_BACKUP_INTERVAL = os.getenv("ONLINE_BACKUP_INTERVAL")
BACKUP_POLL_INTERVAL = os.getenv("BACKUP_POLL_INTERVAL")
RAM = os.getenv("RAM")
CREDENTIALS_FILE_LOCATION = os.getenv("CREDENTIALS_FILE_LOCATION")
CREDENTIALS_JSON = os.getenv("CREDENTIALS_JSON")
JAVA_BIN = os.getenv("JAVA_BIN", "java")

SCOPE_GAME = "[GAME]: " # Will figure out piping with this later (I don't think it will even be performant...)
SCOPE_MC_SERVER_MANAGER = "[MC_SERVER_MANAGER]: "
def log_with_scope(scope, message):
    print(f"{scope} {message}")

def run_mc_server_as_subprocess():
    start_cmd = [JAVA_BIN, f"-Xmx{RAM}", "-jar", "fabric-server-launch.jar", "nogui"]
    global server_process_global
    server_process_global = subprocess.Popen(start_cmd, cwd=LOCAL_SERVER_DIR, stdin=subprocess.PIPE)
    log_with_scope(SCOPE_MC_SERVER_MANAGER, "Minecraft server started.")

    # Print the pids
    log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Server PID: {server_process_global.pid}")
    log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Server Process Group ID: {os.getpgid(server_process_global.pid)}")
    
    #Print this script's PID
    log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Script PID: {os.getpid()}")
    log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Script Process Group ID: {os.getpgrp()}")

def stop_server():
    if server_process_global:
        log_with_scope(SCOPE_MC_SERVER_MANAGER, "Stopping minecraft server...")
        server_process_global.stdin.write('/stop\n'.encode())
        server_process_global.stdin.flush()
        server_process_global.wait()  # Wait for the server to finish
        log_with_scope(SCOPE_MC_SERVER_MANAGER, "Minecraft server stopped.")
    else:
        log_with_scope(SCOPE_MC_SERVER_MANAGER, "ERROR: Server process could not be found.")

def get_service():
    if CREDENTIALS_JSON:
        creds = Credentials.from_service_account_info(json.loads(CREDENTIALS_JSON), scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE_LOCATION, scopes=SCOPES)
    service = build("drive", "v3", credentials=creds)

    return service

def get_root_folder_id():
    results = (
        get_service().files()
        .list(
            q=f"name='{CLOUD_ROOT_FOLDER}' and mimeType='application/vnd.google-apps.folder' and sharedWithMe",
            fields="files(id)",
        )
        .execute()
    )
    root_folder_id = results.get("files", [])[0]["id"]
    return root_folder_id

def build_directory_structure(folder_id, indent=""):
    metadata_results = {}

    # List all files and folders in the current folder
    results = (
        get_service()
        .files()
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
            metadata_results[item["name"]] = build_directory_structure(item["id"], indent + "  ")
            metadata_results[item["name"]]["id"] = item["id"]
        else:
            metadata_results[item["name"]] = item

    return metadata_results

def getLatestCloudBackup():
    # Each backup is 0.zip, 1.zip, 2.zip, etc.
    # Get all keys and sort them
    directory_metadata = build_directory_structure(get_root_folder_id())
    latest_backups = directory_metadata["backups"][CLOUD_SERVER_NAME]
    latest_backups_keys = list(latest_backups.keys())
    latest_backups_keys.remove("id")
    latest_backups_keys.sort()
    latest_backup = latest_backups_keys[-1]
    
    latest_backup_id = latest_backups[latest_backup]["id"]
    latest_backup_name = latest_backups[latest_backup]["name"]
    return latest_backup_id, latest_backup_name

def getLatestLocalBackup():
    if not os.path.exists(LOCAL_BACKUP_DIR):
        os.mkdir(LOCAL_BACKUP_DIR)
        return -1

    # Get all files in the directory
    files = os.listdir(LOCAL_BACKUP_DIR)
    # Filter out all files that are not .zip
    files = [f for f in files if f.endswith(".zip")]
    # Sort the files by name
    files.sort()
    # Return the last file
    return -1 if not files else getBackupIterationFromName(files[-1])

def getBackupIterationFromName(name):
    # Try to get number from name, else return -1
    try:
        return int(name.split(".")[0])
    except:
        return -1
    
def remove_old_cloud_backups():
    service = get_service()

    # Get all cloud backups
    directory_metadata = build_directory_structure(get_root_folder_id())
    backsups = directory_metadata["backups"][CLOUD_SERVER_NAME]
    backsups_keys = list(backsups.keys())
    backsups_keys.remove("id")
    backsups_keys.sort()

    # Get all cloud backups to delete (older than 5 backups, make into env property)
    backups_to_delete_keys = backsups_keys[:-5]
    backsups_to_delete_ids = [backsups[key]["id"] for key in backups_to_delete_keys]

    # Delete them
    for file_id in backsups_to_delete_ids:
        try:
            service.files().delete(fileId=file_id).execute()
        except HttpError as error:
            log_with_scope(SCOPE_MC_SERVER_MANAGER, f"An error occurred while deleting cloud backup file with ID {file_id}: {error}")

    log_with_scope(SCOPE_MC_SERVER_MANAGER, "Finished deleting old cloud backups.")

def clear_zips(directory):
    for filename in os.listdir(directory):
        if filename.endswith(".zip"):
            file_path = os.path.join(directory, filename)
            try:
                os.unlink(file_path)
            except Exception as e:
                log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Failed to delete {file_path}. Reason: {e}")

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
            log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Failed to delete {file_path}. Reason: {e}")

def download_file(
    file_id, destination_folder, destination_file_name="server.zip"
):
    try:
        request = get_service().files().get_media(fileId=file_id)
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Download {int(status.progress() * 100)}.")

        # The file is now in RAM, save to a file at desired path
        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)
        with open(f"{destination_folder}/{destination_file_name}", "wb") as f:
            full_path = os.path.abspath(f.name)
            log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Saving to {full_path}")
            f.write(file.getvalue())

    except HttpError as error:
        log_with_scope(SCOPE_MC_SERVER_MANAGER, f"An error occurred: {error}")
        file = None

def download_latest_cloud_backup():
    latest_cloud_backup_id, latest_cloud_backup_name = getLatestCloudBackup()
    
    if not os.path.exists(LOCAL_SERVER_DIR):
        os.mkdir(LOCAL_SERVER_DIR)

    if getLatestLocalBackup() >= getBackupIterationFromName(latest_cloud_backup_name):
        log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Latest backup already downloaded: {latest_cloud_backup_name}")
    else:
        clear_directory(LOCAL_SERVER_DIR)
        download_file(latest_cloud_backup_id, LOCAL_BACKUP_DIR, latest_cloud_backup_name)

        # Unzip contents directly inside LOCAL_SERVER_DIR
        with zipfile.ZipFile(
            f"{LOCAL_BACKUP_DIR}/{latest_cloud_backup_name}", "r"
        ) as zip_ref:
            zip_ref.extractall(LOCAL_SERVER_DIR)

def upload_cloud_backup(backup_name):
    directory_metadata = build_directory_structure(get_root_folder_id())

    # Upload the zip file to the backups folder
    file_metadata = {
        "name": f"{backup_name}.zip",
        "parents": [directory_metadata["backups"][CLOUD_SERVER_NAME]["id"]],
    }
    # Create a MediaFileUpload object and specify resumable=True
    media = MediaFileUpload(
        f"{LOCAL_BACKUP_DIR}/{backup_name}.zip", 
        mimetype="application/zip", 
        resumable=True
    )

    log_with_scope(SCOPE_MC_SERVER_MANAGER, "Uploading backup file...")
    log_with_scope(SCOPE_MC_SERVER_MANAGER, file_metadata)
    request = get_service().files().create(body=file_metadata, media_body=media, supportsAllDrives=True)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Uploaded {int(status.progress() * 100)}%")

def zip_folder_contents(folder_path, zip_name, output_path=LOCAL_BACKUP_DIR):
    # Zip the contents of the server directory
    with zipfile.ZipFile(f"{output_path}/{zip_name}.zip", "w", compression=zipfile.ZIP_DEFLATED) as zip_ref:
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, folder_path)
                if relative_path == f"{zip_name}.zip":
                    continue  # Skip the zip file itself
                zip_ref.write(file_path, relative_path)
    log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Zipped contents to {zip_name}.zip")

def create_backup(do_online_backup=True):
    # Get index of latest backup from name
    latest_backup_index = getLatestLocalBackup()
    next_index = latest_backup_index + 1
    log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Creating backup #{next_index}")
    
    # Zip the contents of the server directory
    zip_folder_contents(LOCAL_SERVER_DIR, next_index)

    # Upload the zip file to the backups folder
    if do_online_backup:
        upload_cloud_backup(next_index)
        log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Created backup file: {next_index}.zip")

    # Remove old cloud backups
    remove_old_cloud_backups()

def main():
    try:
        # Get the environment variables
        log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Server Name: {CLOUD_SERVER_NAME}")
        log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Local Backup Interval: {LOCAL_BACKUP_INTERVAL}")
        log_with_scope(SCOPE_MC_SERVER_MANAGER, f"Online Backup Interval: {ONLINE_BACKUP_INTERVAL}")
        

        # Get shared folder id by searching for PROD_MC_SERVER
        root_folder_id = get_root_folder_id()

        # Get directory structure and print
        directory_metadata = build_directory_structure(root_folder_id)
        log_with_scope(SCOPE_MC_SERVER_MANAGER, json.dumps(directory_metadata, indent=4))

        # Download the latest backup
        download_latest_cloud_backup()
        
    except Exception as error:
        log_with_scope(SCOPE_MC_SERVER_MANAGER, f"An error occurred while checking for latest cloud backup at initialization: {error}")
        log_with_scope(SCOPE_MC_SERVER_MANAGER, "Continuing using local backups...")

    # Start the server
    run_mc_server_as_subprocess()
    atexit.register(stop_server)
    
    last_local_backup_time = time.time()
    last_online_backup_time = time.time()

    # Schedule backups while the server is running
    while server_process_global and server_process_global.poll() is None:
        time.sleep(int(BACKUP_POLL_INTERVAL))
        do_local_backup = (time.time() - last_local_backup_time) >= int(LOCAL_BACKUP_INTERVAL)
        do_online_backup = (time.time() - last_online_backup_time) >= int(ONLINE_BACKUP_INTERVAL)
        do_backup = do_local_backup or do_online_backup
       
        if do_backup:
            try:
                stop_server()
                create_backup(do_online_backup)
                run_mc_server_as_subprocess()
            except Exception as error:
                log_with_scope(SCOPE_MC_SERVER_MANAGER, f"An error occurred during backup process: {error}")
                log_with_scope(SCOPE_MC_SERVER_MANAGER, "Restarting server without backing up...")
                run_mc_server_as_subprocess()
            last_local_backup_time = time.time()
            last_online_backup_time = time.time() if do_online_backup else last_online_backup_time

    log_with_scope(SCOPE_MC_SERVER_MANAGER, "Server stopped. Exiting...")

if __name__ == "__main__":
    main()
