import multiprocessing as mp
import os
import signal
import selectors
import socket
import time

import server

from typing import Optional


RESET = "\033[0m"
BOLD = "\033[1m"
RED_FG = "\033[31m"
GREEN_FG = "\033[32m"

PASS = GREEN_FG + BOLD + "[Pass]" + RESET
FAIL = RED_FG + BOLD + "[Fail]" + RESET

TESTING_DIR: str = "testing"
SERVER_WAIT: float = 2.
TIMEOUT_TOLERANCE: float = 1.

SERVER_AT: str = "@"
CLIENT_TO: str = "~"
SEND: str = ">"
RECV: str = "<"


class Server:

    instances = []

    def __init__(self, name: str, port: int):
        self.name: str = name
        self.port: int = port

        self.process: mp.Process = mp.Process(target=server.main, args=(port,))
        self.process.start()

        time.sleep(SERVER_WAIT)

        self.instances.append(self)

    def close(self):
        os.kill(self.process.pid, signal.SIGINT)
        time.sleep(SERVER_WAIT)

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
            raise ValueError("Socket not available for write!")
        data: bytes = text.encode()
        sent: int = self.sock.send(data)
        if sent != len(data):
            raise ValueError("Sent data is incomplete!")

    def check_recv(self, text: str):
        self.selector.modify(self.sock, selectors.EVENT_READ)
        if not self.selector.select(TIMEOUT_TOLERANCE):
            raise ValueError("Socket not available for read!")
        data: bytes = self.sock.recv(1024)
        recv: str = data.decode().removesuffix("\n")
        if recv != text:
            raise ValueError("Received text does not match!\n"
                             f"Expecting {text!r},\n"
                             f"Received {recv!r} instead.")

    def close(self):
        self.selector.unregister(self.sock)
        self.sock.close()

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


def test(path: str):
    with open(path) as f:
        for line in f.readlines():
            name, verb, *args = line.split()
            if verb == SERVER_AT:
                if Server.by_name(name) is not None:
                    raise ValueError(f"there exists a server named {name}")
                Server(name, int(args[0]))
            elif verb == CLIENT_TO:
                if Client.by_name(name) is not None:
                    raise ValueError(f"there exists a client named {name}")
                Client(name, Server.by_name(args[0]).port)
            elif verb == SEND:
                if Client.by_name(name) is None:
                    raise ValueError(f"there exists no client named {name}")
                Client.by_name(name).check_send(" ".join(args))
            elif verb == RECV:
                if Client.by_name(name) is None:
                    raise ValueError(f"there exists no client named {name}")
                Client.by_name(name).check_recv(" ".join(args))


def main():
    for path in sorted(os.listdir(TESTING_DIR)):
        name: str = path[:path.index('.')].replace('_', ' ').title()
        try:
            test(os.path.join(TESTING_DIR, path))
        except Exception as e:
            print(f"{FAIL} {name}")
            # Display error message indented.
            print("\t" + type(e).__name__)
            print(*map(lambda s: "\t" + s, str(e).split("\n")), sep='\n')
        else:
            print(f"{PASS} {name}")
        finally:
            Client.clear_all()
            Server.clear_all()


if __name__ == '__main__':
    main()
