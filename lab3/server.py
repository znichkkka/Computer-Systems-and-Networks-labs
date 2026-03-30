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

class Server:
    Clients = []

    def __init__(self, HOST, PORT):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.socket.bind((HOST, PORT))
        except OSError:
            print("Не удалось запустить сервер: порт занят или IP указан неверно.")
            self.socket.close()
            raise

        self.host = HOST
        self.socket.listen(5)
        print(f"Сервер запущен на {HOST}:{PORT}")
        print("Ожидание подключений...")


    def listen(self):
        while True:
            client_socket, address = self.socket.accept()

            print("Подключение от: " + str(address))

            client_name = client_socket.recv(1024).decode()
            client = {'client_name': client_name, 'client_socket': client_socket}

            self.broadcast_message(client_name, client_name + " присоединился к чату!")

            Server.Clients.append(client)
            Thread(target=self.handle_new_client, args = (client,)).start()

    def handle_new_client(self, client):
        client_name = client['client_name']
        client_socket = client['client_socket']

        while True:
            try:
                client_message = client_socket.recv(1024).decode()
            except OSError:
                client_message = ""

            if client_message.strip() == client_name + ": bye" or not client_message.strip():
                self.broadcast_message(client_name, client_name + " покинул чат!")
                if client in Server.Clients:
                    Server.Clients.remove(client)
                try:
                    client_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                client_socket.close()
                break
            else:
                self.broadcast_message(client_name, client_message)

    def broadcast_message(self, sender_name, message):
        for client in self.Clients:
            client_socket = client['client_socket']
            client_name = client['client_name']
            if client_name != sender_name:
                try:
                    client_socket.send(message.encode())
                except OSError:
                    pass


if __name__ == '__main__':
    host = input("Введите IP сервера: ").strip()
    port = input_port("Введите порт сервера: ")

    server = Server(host, port)
    server.listen()
