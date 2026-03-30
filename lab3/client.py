import socket
from threading import Thread


def input_port(prompt):
    while True:
        value = input(prompt).strip()
        if not value.isdigit():
            print("Порт должен быть числом.")
            continue

        port = int(value)
        if 1024 <= port <= 65535:
            return port
        else:
            print("Используйте порт от 1024 до 65535.")

class Client:

    def __init__(self, SERVER_HOST, SERVER_PORT, CLIENT_HOST, CLIENT_PORT):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.socket.bind((CLIENT_HOST, CLIENT_PORT))
        except OSError:
            print("Не удалось привязать клиент к выбранному локальному IP/порту.")
            self.socket.close()
            return
        try:
            self.socket.connect((SERVER_HOST, SERVER_PORT))
        except OSError:
            print("Не удалось подключиться к серверу.")
            self.socket.close()
            return

        while True:
            self.name = input("Введите имя: ").strip()
            if self.name:
                break
            print("Имя не должно быть пустым.")

        self.talk_to_server()

    def talk_to_server(self):
        self.socket.send(self.name.encode())
        Thread(target=self.recieve_message, daemon=True).start()
        self.send_message()

    def send_message(self):
        while True:
            client_input = input("")

            if client_input.lower() == "bye":
                try:
                    self.socket.send((self.name + ": bye").encode())
                except OSError:
                    pass
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.socket.close()
                break

            try:
                client_message = self.name + ": " + client_input
                self.socket.send(client_message.encode())
            except OSError:
                print("Соединение потеряно.")
                break

    def recieve_message(self):
        while True:
            try:
                server_message = self.socket.recv(1024).decode()
            except OSError:
                print("Сервер недоступен.")
                break

            if not server_message.strip():
                print("Сервер закрыл соединение.")
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.socket.close()
                break
            else:
                print("\033[1;31;40m" + server_message + "\033[0m")


if __name__ == '__main__':
    server_host = input("Введите IP сервера: ").strip()
    server_port = input_port("Введите порт сервера: ")

    client_host = input("Введите локальный IP клиента: ").strip()
    client_port = input_port("Введите локальный порт клиента: ")

    Client(server_host, server_port, client_host, client_port)