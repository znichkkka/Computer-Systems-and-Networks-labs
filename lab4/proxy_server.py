import socket
import threading
from urllib.parse import urlsplit

PROXY_HOST = "127.0.0.2"
PROXY_PORT = 5000
BUFFER_SIZE = 4096
BLACKLIST_FILE = "blacklist.txt"

HTTP_STATUS_TEXTS = {
    200: "OK",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway"
}

def load_blacklist(filename):
    blocked_domains = set()
    blocked_urls = set()

    try:
        with open(filename, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                if line.startswith("http://"):
                    blocked_urls.add(line.lower())
                else:
                    blocked_domains.add(line.lower())
    except FileNotFoundError:
        print(f"Файл конфигурации {filename} не найден. Чёрный список будет пустым.")

    return blocked_domains, blocked_urls


def is_blocked(url, host, blocked_domains, blocked_urls):
    url = url.lower()
    host = host.lower()

    if url in blocked_urls or host in blocked_domains:
        return True

    for blocked_domain in blocked_domains:
        if host == blocked_domain or host.endswith("." + blocked_domain):
            return True

    return False


def send_blocked_response(client_socket, url):
    response = (
        "HTTP/1.1 403 Forbidden\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Connection: close\r\n"
        "\r\n"
        f"<html><body><h1>Доступ к ресурсу запрещён</h1>"
        f"<p>Адрес: {url}</p></body></html>"
    )

    try:
        client_socket.sendall(response.encode("utf-8"))
    except OSError:
        pass


def send_error_response(client_socket, status_code):
    status_text = HTTP_STATUS_TEXTS.get(status_code, "Error")

    response = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Connection: close\r\n"
        "\r\n"
        f"<html><body><h1>{status_code} {status_text}</h1></body></html>"
    )

    try:
        client_socket.sendall(response.encode("utf-8"))
    except OSError:
        pass


def receive_request(client_socket):
    request_data = b""

    while True:
        data = client_socket.recv(BUFFER_SIZE)
        if not data:
            break

        request_data += data
        if b"\r\n\r\n" in request_data:
            break

    return request_data


def parse_request(request_data):
    try:
        request_text = request_data.decode("iso-8859-1", errors="replace")
        lines = request_text.split("\r\n")
        if not lines:
            return None

        request_line = lines[0]
        parts = request_line.split()
        if len(parts) < 3:
            return None

        method = parts[0]
        url = parts[1]

        headers = {}

        for i in range(1, len(lines)):
            line = lines[i]

            if line == "":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        return  method, url, headers

    except Exception:
        return None


def get_host_port_and_path(url, headers):
    host = ""
    port = 80
    path = "/"

    if url.startswith("http://"):
        parsed_url = urlsplit(url)

        host = parsed_url.hostname or ""
        port = parsed_url.port or 80
        path = parsed_url.path
        if not path:
            path = "/"
        if parsed_url.query:
            path += "?" + parsed_url.query

    else:
        host_header = headers.get("host", "")
        if not host_header:
            return None
        if ":" in host_header:
            host, port_text = host_header.split(":", 1)
            port = int(port_text)
        else:
            host = host_header
        path = url if url else "/"

    return host, port, path


def build_server_request(request_data, method, path):
    request_text = request_data.decode("iso-8859-1", errors="replace")
    lines = request_text.split("\r\n")
    if not lines:
        return None

    parts = lines[0].split()
    if len(parts) < 3:
        return None

    http_version = parts[2]
    new_lines = [f"{method} {path} {http_version}"]

    has_connection_header = False

    for line in lines[1:]:
        if line == "":
            continue

        lower_line = line.lower()

        if lower_line.startswith("proxy-connection:"):
            continue

        if lower_line.startswith("connection:"):
            new_lines.append("Connection: close")
            has_connection_header = True
            continue

        new_lines.append(line)

    if not has_connection_header:
        new_lines.append("Connection: close")

    new_request_text = "\r\n".join(new_lines) + "\r\n\r\n"
    return new_request_text.encode("iso-8859-1")


def forward_server_response(server_socket, client_socket, url):
    response_code = None
    response_text = ""
    first_piece = True

    while True:
        try:
            data = server_socket.recv(BUFFER_SIZE)
        except OSError:
            break

        if not data:
            break

        if first_piece:
            try:
                text = data.decode("iso-8859-1", errors="replace")
                lines = text.split("\r\n")
                response_line = lines[0]
                parts = response_line.split(" ", 2)

                if len(parts) >= 3:
                    response_code = int(parts[1])
                    response_text = parts[2]
            except Exception:
                response_code = None
                response_text = ""

            if "detectportal.firefox.com" not in url and not url.endswith("/favicon.ico"):
                if response_code is not None:
                    print(f"{url} - {response_code} {response_text}")
                else:
                    print(f"{url} - код ответа не определён")

            first_piece = False

        try:
            client_socket.sendall(data)
        except OSError:
            break

    return response_code, response_text


def handle_client(client_socket, blocked_domains, blocked_urls):
    server_socket = None

    try:
        request_data = receive_request(client_socket)
        if not request_data:
            return

        parsed_request = parse_request(request_data)
        if parsed_request is None:
            send_error_response(client_socket, 400)
            print("неизвестный URL - 400 Bad Request")
            return

        method, url, headers = parsed_request

        if method.upper() == "CONNECT":
            send_error_response(client_socket, 501)
            return

        target_info = get_host_port_and_path(url, headers)
        if target_info is None:
             send_error_response(client_socket, 400)
             print(f"{url} - 400 Bad Request")
             return

        host, port, path = target_info
        if not host:
            send_error_response(client_socket, 400)
            print(f"{url} - 400 Bad Request")
            return

        if is_blocked(url, host, blocked_domains, blocked_urls):
            send_blocked_response(client_socket, url)
            if not url.endswith("/favicon.ico"):
                print(f"{url} - 403 Forbidden")
            return

        server_request = build_server_request(request_data, method, path)
        if server_request is None:
            send_error_response(client_socket, 400)
            print(f"{url} - 400 Bad Request")
            return

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect((host, port))
        server_socket.sendall(server_request)

        forward_server_response(server_socket, client_socket, url)

    except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
        pass
    except Exception:
        send_error_response(client_socket, 500)
        print("ошибка обработки запроса - 500 Internal Server Error")
    finally:
        if server_socket:
            try:
                server_socket.close()
            except OSError:
                pass

        try:
            client_socket.close()
        except OSError:
            pass


def start_proxy_server():
    blocked_domains, blocked_urls = load_blacklist(BLACKLIST_FILE)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((PROXY_HOST, PROXY_PORT))
    server.listen(5)

    print(f"Прокси запущен на {PROXY_HOST}:{PROXY_PORT}")

    try:
        while True:
            client_socket, client_address = server.accept()
            thread = threading.Thread(target=handle_client, args=(client_socket, blocked_domains, blocked_urls), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("Сервер остановлен")
    finally:
        server.close()


if __name__ == "__main__":
    start_proxy_server()








