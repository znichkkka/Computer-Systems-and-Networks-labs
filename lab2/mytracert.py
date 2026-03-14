import argparse
import os
import socket
import struct
import time


ICMP_ECHO_REQUEST = 8
ICMP_ECHO_REPLY = 0
ICMP_TIME_EXCEEDED = 11

MAX_HOPS = 30
PROBES_PER_HOP = 3
TIMEOUT = 3.0
DATA = b"abcdefghijklmnopqrstuvwabcdefghi"

IDENTIFIER = os.getpid() & 0xFFFF


def calculate_checksum(data: bytes) -> int:
    total = 0

    if len(data) % 2 != 0:
        data += b"\x00"

    for i in range(0, len(data), 2):
        total += (data[i] << 8) + data[i + 1]

    while total > 0xFFFF:
        total = (total & 0xFFFF) + (total >> 16)

    return (~total) & 0xFFFF


def create_icmp_request(identifier: int, sequence: int) -> bytes:
    icmp_type = ICMP_ECHO_REQUEST
    icmp_code = 0
    icmp_checksum = 0

    header = struct.pack("!BBHHH", icmp_type, icmp_code, icmp_checksum, identifier, sequence)
    icmp_checksum = calculate_checksum(header + DATA)
    header = struct.pack("!BBHHH", icmp_type, icmp_code, icmp_checksum, identifier, sequence)

    return header + DATA


def get_target_ip(target: str) -> str:
    try:
        return socket.gethostbyname(target)
    except socket.gaierror:
        print(f"Не удалось определить IP-адрес узла {target}.")
        raise SystemExit(1)


def get_host_name(ip: str, use_dns: bool) -> str:
    if not use_dns:
        return ip

    try:
        host = socket.gethostbyaddr(ip)[0]
        return f"{host} [{ip}]"
    except (socket.herror, socket.gaierror):
        return ip


def get_target_text(target: str, target_ip: str, use_dns: bool) -> str:
    if target != target_ip:
        return f"{target} [{target_ip}]"
    return get_host_name(target_ip, use_dns)


def get_ip_header_length(packet: bytes) -> int:
    if len(packet) < 20:
        return 0

    version = packet[0] >> 4
    if version != 4:
        return 0

    header_length = (packet[0] & 0x0F) * 4
    if header_length < 20 or len(packet) < header_length:
        return 0

    return header_length


def read_icmp_header(packet: bytes, start: int):
    if len(packet) < start + 8:
        return None

    return struct.unpack("!BBHHH", packet[start:start + 8])


def get_reply_type(packet: bytes, expected_identifier: int, expected_sequence: int):
    outer_ip_length = get_ip_header_length(packet)
    if outer_ip_length == 0:
        return None

    outer_icmp = read_icmp_header(packet, outer_ip_length)
    if outer_icmp is None:
        return None

    icmp_type, icmp_code, icmp_checksum, identifier, sequence = outer_icmp

    if icmp_type == ICMP_ECHO_REPLY:
        if identifier == expected_identifier and sequence == expected_sequence:
            return "reply"
        return None

    if icmp_type != ICMP_TIME_EXCEEDED:
        return None

    inner_ip_start = outer_ip_length + 8
    inner_ip_length = get_ip_header_length(packet[inner_ip_start:])
    if inner_ip_length == 0:
        return None

    inner_icmp_start = inner_ip_start + inner_ip_length
    inner_icmp = read_icmp_header(packet, inner_icmp_start)
    if inner_icmp is None:
        return None

    inner_type, inner_code, inner_checksum, inner_identifier, inner_sequence = inner_icmp

    if inner_type == ICMP_ECHO_REQUEST and inner_identifier == expected_identifier and inner_sequence == expected_sequence:
        return "ttl"

    return None


def send_one_packet(target_ip: str, ttl: int, sequence: int, timeout: float):
    request_packet = create_icmp_request(IDENTIFIER, sequence)

    sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
    sock.settimeout(timeout)

    try:
        start_time = time.perf_counter()
        sock.sendto(request_packet, (target_ip, 0))

        while True:
            reply_packet, reply_address = sock.recvfrom(65535)
            end_time = time.perf_counter()

            reply_type = get_reply_type(reply_packet, IDENTIFIER, sequence)
            if reply_type is None:
                continue

            return {
                "success": True,
                "ip": reply_address[0],
                "time_ms": (end_time - start_time) * 1000.0,
                "reply_type": reply_type
            }

    except socket.timeout:
        return {
            "success": False,
            "ip": None,
            "time_ms": None,
            "reply_type": None
        }
    finally:
        sock.close()


def format_time(time_ms: float) -> str:
    if time_ms < 1:
        return "<1 мс"
    return f"{round(time_ms)} мс"


def print_result_line(ttl: int, times, addresses, use_dns: bool):
    print(f"{ttl:>2}", end="    ")

    for value in times:
        print(f"{value:>8}", end="")

    if addresses:
        print(f"    {get_host_name(addresses[-1], use_dns)}")
    else:
        print("    Превышен интервал ожидания для запроса.")


def trace_route(target: str, use_dns: bool, max_hops: int, timeout: float):
    target_ip = get_target_ip(target)

    print(f"Трассировка маршрута к {get_target_text(target, target_ip, use_dns)}")
    print(f"с максимальным числом прыжков {max_hops}:\n")

    sequence = 0

    for ttl in range(1, max_hops + 1):
        times = []
        addresses = []
        target_reached = False

        for _ in range(PROBES_PER_HOP):
            sequence += 1
            result = send_one_packet(target_ip, ttl, sequence, timeout)

            if not result["success"]:
                times.append("*")
                continue

            times.append(format_time(result["time_ms"]))
            addresses.append(result["ip"])

            if result["reply_type"] == "reply" and result["ip"] == target_ip:
                target_reached = True

        print_result_line(ttl, times, addresses, use_dns)

        if target_reached:
            print("\nТрассировка завершена.")
            return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="IP-адрес или имя узла")
    parser.add_argument("-d", action="store_true", help="включить разрешение адресов узлов в DNS-имена")

    args = parser.parse_args()

    try:
        trace_route(
            target=args.target,
            use_dns=args.d,
            max_hops=MAX_HOPS,
            timeout=TIMEOUT
        )
    except PermissionError:
        print("Ошибка: программу нужно запускать от имени администратора.")
    except KeyboardInterrupt:
        print("\nТрассировка прервана пользователем.")


if __name__ == "__main__":
    main()