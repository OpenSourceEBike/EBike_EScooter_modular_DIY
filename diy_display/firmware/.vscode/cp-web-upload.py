import sys
import os
import requests
from dotenv import load_dotenv
load_dotenv()

# Get variables from .env file
url = os.getenv("URL")
password = os.getenv("CIRCUITPY_WEB_API_PASSWORD")
device_files_folders_to_ignore = os.getenv("DEVICE_FILES_FOLDERS_TO_IGNORE").split(",")
device_files_folders_to_ignore = [folder.strip() for folder in device_files_folders_to_ignore]
project_files_folders_to_ignore = os.getenv("PROJECT_FILES_FOLDERS_TO_IGNORE", "").split(",")
project_files_folders_to_ignore = [folder.strip() for folder in project_files_folders_to_ignore]

baseURL = "http://" + url + "/fs"

def get_all_files_from_device(base_url, path='', files=None):

    if files is None:
        files = {}

    path_url = base_url + '/' + path
    response = requests.get(path_url, auth=("", password), headers={"Accept": "application/json"})

    if response.status_code == 200:
        try:
            data = response.json()
            for file in data.get("files", []):                
                if file.get("directory", True):  # If it's a directory, call recursively
                    get_all_files_from_device(base_url, path=file['name'] + '/', files=files)
                else:
                    full_file_name = path + file['name']
                    if full_file_name not in files:  # Prevent adding already existing files
                        files[full_file_name] = {'file_size': file['file_size'], 'modified_ns': file['modified_ns']}
  
            return files  # Return the updated files dictionary

        except ValueError:
            print("Error: Unable to parse JSON response.")
    else:
        print(f"Error {response.status_code}: {response.reason}")

    return files

def get_all_files_from_project_folder(path='.', files=None):
    if files is None:
        files = {}

    for root, _, file_names in os.walk(path):
        for file_name in file_names:
            full_file_path = os.path.join(root, file_name)
            relative_file_name = os.path.relpath(full_file_path, path)
            file_stat = os.stat(full_file_path)

            if relative_file_name not in files:  # Prevent duplicates
                files[relative_file_name] = {
                    'file_size': file_stat.st_size,
                    'modified_ns': file_stat.st_mtime_ns
                }

    return files  # Return the dictionary in the same format as the device function

def filter_files_folders(files_folders_dict, filter_list):

    return {file_name: file_info for file_name, file_info in files_folders_dict.items()
            if not any(ignored in file_name for ignored in filter_list)}

def filter_files_folders_by_date_higher(files_folders_dict, filter_list_dict):
    filtered_files = {}

    for file_name, file_info in files_folders_dict.items():
        should_ignore = False
        
        # Check if the file name is in the filter list dictionary
        for ignored_file_name, ignored_file_info in filter_list_dict.items():
            if ignored_file_name in file_name:
                # If the file name is in the ignored list, compare modification dates
                if file_info['modified_ns'] <= ignored_file_info['modified_ns']:
                    should_ignore = True
                    break
        
        # If the file should not be ignored, add it to the filtered_files dictionary
        if not should_ignore:
            filtered_files[file_name] = file_info

    return filtered_files


def create_parent_directory(relative_path):
    relative_path = relative_path.removesuffix("/")
    print("Creating parent directory for:",relative_path)
    directory = relative_path.replace(relative_path.split("/")[-1],"")
    dir_response = requests.put(baseURL + directory, auth=("",password))
    if(dir_response.status_code == 201):
        print("Directory created:", directory)
    else:
        print(dir_response.status_code, dir_response.reason)


############################################################################
#
# The idea is to mirror the project files and folders to the CircuitPyhton
# device memory - example ESP32-C3.
#
# Steps:
#
#   1. Get a list of all device folders and files
#
#   2. Get a list of all project folders and files
#
#   3. Remove all files and folders on the device that do not exist on the project.
#      Ignore the DEVICE_FILES_FOLDERS_TO_IGNORE.
#
#   4. Copy all files and folders from the project to the device that do not exist on the device.
#      Ignore the PROJECT_FILES_FOLDERS_TO_IGNORE.


# Following the # CircuitPython Files Rest API:
# https://docs.circuitpython.org/en/latest/docs/workflows.html


# Get a list of all device folders and files
device_files = get_all_files_from_device(baseURL)
device_files_without_ignored = filter_files_folders(device_files, device_files_folders_to_ignore)

# Get a list of all project folders and files
project_files = get_all_files_from_project_folder()
project_files_without_ignored = filter_files_folders(project_files, project_files_folders_to_ignore)


# first copy local files to device
files_to_copy = filter_files_folders_by_date_higher(project_files_without_ignored, device_files)

# remove files on device that do not exist locally
files_to_remove = filter_files_folders_by_date_higher(project_files_without_ignored, device_files)

if files_to_copy:
    for file_name, file_info in files_to_copy.items():
        print(f"{file_name}, {file_info['file_size']}, {file_info['modified_ns']}")

# response = requests.put(baseURL + relativeFile, data=open(workspaceFolder + "/" + relativeFile,"rb"), auth=("",password))
# if(response.status_code ==  201):
#     print("Created file:", relativeFile)
# elif(response.status_code == 204):
#     print("Overwrote file:", relativeFile)
# elif(response.status_code == 401):
#     print("Incorrect password")
# elif(response.status_code == 403):
#     print("CIRCUITPY_WEB_API_PASSWORD not set")
# elif(response.status_code == 404):
#     print("Missing parent directory")
#     create_parent_directory(relativeFile)
#     retry_response = requests.put(baseURL + relativeFile, data=open(workspaceFolder + "/" + relativeFile,"rb"), auth=("",password))
#     if(retry_response.status_code ==  201):
#         print("Created file:", relativeFile)
#     else:
#         print(retry_response.status_code, retry_response.reason)
# elif(response.status_code == 409):
#     print("USB is active and preventing file system modification")
# else:
#     print(response.status_code, response.reason)

