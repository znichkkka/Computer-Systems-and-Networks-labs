import os
import time
from flask import Flask, request, jsonify, Response, send_file

app = Flask(__name__)

STORAGE_DIR = "storage"

def create_storage():
    if not os.path.exists(STORAGE_DIR):
        os.mkdir(STORAGE_DIR)


def get_full_path(path):
    path = path.strip("/")

    storage_path = os.path.abspath(STORAGE_DIR)
    full_path = os.path.abspath(os.path.join(STORAGE_DIR, path))

    if os.path.commonpath([storage_path, full_path]) != storage_path:
        return None

    return full_path


def create_folder_for_file(full_path):
    folder = os.path.dirname(full_path)

    if not os.path.exists(folder):
        os.makedirs(folder)


def save_file(full_path):
    file_exists = os.path.exists(full_path)

    create_folder_for_file(full_path)

    with open(full_path, "wb") as file:
        file.write(request.data)

    if file_exists:
        return Response("File saved", status=200)

    return Response("File created", status=201)


def copy_file(full_path, copy_from):
    source_path = get_full_path(copy_from)

    if source_path is None:
        return Response("Bad source path", status=400)

    if source_path == full_path:
        return Response("Cannot copy file to itself", status=400)

    if not os.path.isfile(source_path):
        return Response("Source file not found", status=404)

    file_exists = os.path.exists(full_path)

    create_folder_for_file(full_path)

    with open(source_path, "rb") as source_file:
        data = source_file.read()

    with open(full_path, "wb") as new_file:
        new_file.write(data)

    if file_exists:
        return Response("File copied", status=200)

    return Response("File copied", status=201)


def get_file_or_directory(full_path):
    if os.path.isfile(full_path):
        return send_file(full_path)

    if os.path.isdir(full_path):
        items = []

        for name in os.listdir(full_path):
            item_path = os.path.join(full_path, name)

            if os.path.isfile(item_path):
                item_type = "file"
            else:
                item_type = "directory"

            items.append({
                "name": name,
                "type": item_type
            })

        return jsonify(items), 200

    return Response("Not found", status=404)


def get_file_info(full_path):
    if not os.path.exists(full_path):
        return Response(status=404)

    response = Response(status=200)

    if os.path.isfile(full_path):
        file_size = os.path.getsize(full_path)
        last_modified = os.path.getmtime(full_path)

        response.headers["Content-Length"] = str(file_size)
        response.headers["X-File-Size-Bytes"] = str(file_size)
        response.headers["Last-Modified"] = time.ctime(last_modified)
        response.headers["X-File-Modified-Timestamp"] = str(last_modified)

    elif os.path.isdir(full_path):
        response.headers["Content-Type"] = "application/json"

    return response


def delete_directory(path):
    for root, dirs, files in os.walk(path, topdown=False):
        for file_name in files:
            os.remove(os.path.join(root, file_name))

        for dir_name in dirs:
            os.rmdir(os.path.join(root, dir_name))

    os.rmdir(path)


def delete_file_or_directory(full_path):
    if os.path.isfile(full_path):
        os.remove(full_path)
        return Response(status=204)

    if os.path.isdir(full_path):
        delete_directory(full_path)
        return Response(status=204)

    return Response("Not found", status=404)


@app.route("/", defaults={"path": ""}, methods=["GET", "PUT", "DELETE", "HEAD"])
@app.route("/<path:path>", methods=["GET", "PUT", "DELETE", "HEAD"])
def storage(path):
    create_storage()

    full_path = get_full_path(path)

    if full_path is None:
        return Response("Bad path", status=400)

    if request.method == "GET":
        return get_file_or_directory(full_path)

    if request.method == "HEAD":
        return get_file_info(full_path)

    if request.method == "PUT":
        if path == "":
            return Response("File path is required", status=400)

        copy_from = request.headers.get("X-Copy-From")

        if copy_from:
            return copy_file(full_path, copy_from)

        return save_file(full_path)

    if request.method == "DELETE":
        if path == "":
            return Response("Root directory cannot be deleted", status=400)

        return delete_file_or_directory(full_path)


if __name__ == "__main__":
    create_storage()
    app.run(debug=True)