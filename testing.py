import json
import multiprocessing as mp
import os
import signal
import selectors
import socket
import sys
import time

from server import server

from typing import Optional


RESET = "\033[0m"
BOLD = "\033[1m"
RED_FG = "\033[31m"
GREEN_FG = "\033[32m"
GRAY_FG = "\33[90m"

RUNNING = GRAY_FG + BOLD + "[Running]" + RESET
PASSED = GREEN_FG + BOLD + "[Passed] " + RESET
FAILED = RED_FG + BOLD + "[Failed] " + RESET
IGNORED = GRAY_FG + BOLD + "[Ignored] " + RESET
CLEANING = GRAY_FG + BOLD + "[Cleaning]" + RESET

TESTING_DIR: str = "testing"
JSON_PATH: str = "testing.json"
SOCKET_WAIT: float = 1.0
TIMEOUT_TOLERANCE: float = 1.0

SERVER_AT: str = "@"
CLIENT_TO: str = "~"
SEND: str = ">"
RECV: str = "<"
CLOSE: str = "!"


class FailTest(Exception):
    pass


class InvalidTest(Exception):

    def __init__(self, message, line_no):
        super().__init__(message)
        self.line_no = line_no

    def __str__(self):
        if self.line_no != -1:
            return f"Line {self.line_no} is invalid!\n" + super().__str__()
        else:
            return super().__str__()


class Server:

    instances = []

    def __init__(self, name: str, port: int):
        self.name: str = name
        self.port: int = port

        self.process: mp.Process = mp.Process(target=server, args=(port,))
        self.process.start()

        time.sleep(SOCKET_WAIT)

        self.instances.append(self)

    def close(self):
        os.kill(self.process.pid, signal.SIGINT)
        time.sleep(SOCKET_WAIT)

    @classmethod
    def by_name(cls, name: str) -> Optional["Server"]:
        for instance in cls.instances:
            if instance.name == name:
                return instance

    @classmethod
    def close_all(cls):
        for instance in cls.instances:
            instance.close()

    @classmethod
    def clear_all(cls):
        cls.close_all()
        cls.instances.clear()


class Client:

    instances = []

    def __init__(self, name: str, port: int):
        self.name: str = name
        self.port: int = port

        self.sock: socket.socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(("localhost", self.port))
        self.sock.setblocking(False)

        self.selector: selectors.BaseSelector = selectors.DefaultSelector()
        self.selector.register(self.sock, selectors.EVENT_READ)

        self.instances.append(self)

    def check_send(self, text: str):
        self.selector.modify(self.sock, selectors.EVENT_WRITE)
        if not self.selector.select(TIMEOUT_TOLERANCE):
            raise FailTest("Server socket is not available for write!")
        data: bytes = text.encode()
        sent: int = self.sock.send(data)
        if sent != len(data):
            raise FailTest("Server socket can not accept any more data!")

    def check_recv(self, text: str):
        self.selector.modify(self.sock, selectors.EVENT_READ)
        if not self.selector.select(TIMEOUT_TOLERANCE):
            raise FailTest("Socket not available for read!")
        data: bytes = self.sock.recv(1024)
        recv: str = data.decode().removesuffix("\n")
        if recv != text:
            raise FailTest("Received text does not match!\n"
                           f"Expecting {text!r},\n"
                           f"Received {recv!r} instead.")

    def close(self):
        if self.sock.fileno() != -1:
            self.selector.unregister(self.sock)
            self.sock.close()
            time.sleep(SOCKET_WAIT)

    @classmethod
    def by_name(cls, name: str) -> Optional["Client"]:
        for instance in cls.instances:
            if instance.name == name:
                return instance

    @classmethod
    def close_all(cls):
        for instance in cls.instances:
            instance.close()

    @classmethod
    def clear_all(cls):
        cls.close_all()
        cls.instances.clear()


def load(path):
    try:
        with open(path) as f:
            return f.readlines()
    except FileNotFoundError:
        raise InvalidTest("Unable to load the test case!")


def server_at(name, args, line_no):
    if Server.by_name(name) is not None:
        raise InvalidTest(f"There exists a server named {name}.", line_no)
    if not args:
        raise InvalidTest("Missing server port to bind with.", line_no)
    port = args[0]
    if not port.isdigit():
        raise InvalidTest("Server port must be integer.", line_no)
    port = int(port)
    if not 1 <= port <= 65535:
        raise InvalidTest("Server port must be between 1-65535.", line_no)
    Server(name, port)


def client_to(name, args, line_no):
    if Client.by_name(name) is not None:
        raise InvalidTest(f"There exists a client named {name}.",
                          line_no=line_no)
    elif not args:
        raise InvalidTest("Missing server name to connect to.",
                          line_no=line_no)
    Client(name, Server.by_name(args[0]).port)


def client_action(name, action, args, line_no):
    client = Client.by_name(name)
    if client is None:
        raise InvalidTest(f"There exists no client named {name}.", line_no)
    if action == SEND:
        client.check_send(" ".join(args))
    elif action == RECV:
        client.check_recv(" ".join(args))
    elif action == CLOSE:
        client.close()


def test(path):
    lines = load(path)
    for line_no, line in enumerate(lines):
        # Ignore comments and split tokens.
        tokens = line.strip().partition("#")[0].split()
        if not tokens:
            # Ignore empty lines
            continue
        elif len(tokens) < 2:
            raise InvalidTest("Missing action symbol.", line_no)

        name, action, *args = tokens
        if action == SERVER_AT:
            server_at(name, args, line_no)
        elif action == CLIENT_TO:
            client_to(name, args, line_no)
        elif action in (SEND, RECV, CLOSE):
            client_action(name, action, args, line_no)
        else:
            raise InvalidTest(f"Unknown action symbol {action}.", line_no)


def error(exception, with_type=False):
    if with_type:
        print("\t Unhandled exception: " + type(exception).__name__)
    for line in str(exception).split("\n"):
        print("\t" + line)


def main():
    records = []
    exit_status = 0

    paths = sorted(os.listdir(TESTING_DIR))
    if len(sys.argv) >= 2:
        pattern = sys.argv[1]
        paths = filter(lambda s: pattern in s, paths)

    for path in paths:
        name: str = path.removesuffix(".txt").replace('_', ' ').title()
        print(f"{RUNNING} {name}", end="\r")
        try:
            test(os.path.join(TESTING_DIR, path))
        except InvalidTest as e:
            print(f"{IGNORED} {name}")
            records.append({name: "Ignored"})
            error(e)
        except Exception as e:
            print(f"{FAILED} {name}")
            records.append({name: "Failed"})
            error(e, with_type=isinstance(e, FailTest))
            exit_status = 1
        else:
            print(f"{PASSED} {name}")
            records.append({name: "Passed"})
        finally:
            print(f"{CLEANING}", end="\r")
            Client.clear_all()
            Server.clear_all()

    with open(JSON_PATH, "w") as f:
        json.dump(records, f)
    print(f"Testing records are dumped into {JSON_PATH}.")

    sys.exit(exit_status)


if __name__ == '__main__':
    main()
