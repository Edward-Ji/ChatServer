#!/bin/python
import logging
import os
import selectors
import signal
import socket
import sys

from hashlib import pbkdf2_hmac
from typing import Callable, List, Optional


logging.basicConfig(level=logging.DEBUG)

selector: selectors.BaseSelector = selectors.DefaultSelector()


class User:

    instances: List["User"] = []

    def __init__(self, name: str, passwd: str):
        self.name: str = name
        self._salt: bytes = os.urandom(16)
        self._passhash: bytes = pbkdf2_hmac("sha256",
                                            passwd.encode(),
                                            self._salt,
                                            1000)
        self.logged_in: bool = False
        self.instances.append(self)

    @classmethod
    def register(cls, name: str, passwd: str) -> Optional["User"]:
        for user in cls.instances:
            if user.name == name:
                return None
        user: "User" = User(name, passwd)
        user.logged_in = True
        return user

    def login(self, passwd: str) -> bool:
        if self.logged_in:
            return False
        passhash: bytes = pbkdf2_hmac("sha256",
                                      passwd.encode(),
                                      self._salt,
                                      1000)
        if self._passhash == passhash:
            self.logged_in = True
        return self.logged_in

    def logout(self):
        self.logged_in = False


class Session:

    def __init__(self):
        self._user: User = None
        self.pending: List[str] = []
        self.replies: List[str] = []

    def switch_user(self, user: User):
        self.logout()
        self._user = user

    def register(self, name: str, passwd: str) -> bool:
        user = User.register(name, passwd)
        if user is not None:
            self.switch_user(user)
            return True
        return False

    def login(self, name: str, passwd: str) -> bool:
        for user in User.instances:
            if user.name == name:
                if user.login(passwd):
                    self.switch_user(user)
                    return True
                break
        return False

    def logout(self):
        if self._user is not None:
            self._user.logout()

    def handle(self):
        while self.pending:
            self.replies.append(handle(self, self.pending.pop()))


def check_n_args(*n_args: int) -> Callable:
    min_n_args: int = None
    max_n_args: int = None
    if len(n_args) == 0:
        max_n_args = 0
    elif len(n_args) == 1:
        min_n_args, = max_n_args, = n_args
    elif len(n_args) == 2:
        min_n_args, max_n_args = n_args

    def decorator(func: Callable) -> Callable:
        def wrapper(session: Session, tokens: List[str]) -> str:
            if min_n_args is not None and len(tokens) < min_n_args:
                return "ERROR not enough arguments"
            if max_n_args is not None and len(tokens) > max_n_args:
                return "ERROR too many arguments"
            return func(session, tokens)
        return wrapper
    return decorator


@check_n_args(2)
def register(session: Session, tokens: List[str]) -> str:
    return int(session.register(*tokens))


@check_n_args(2)
def login(session: Session, tokens: List[str]) -> str:
    return int(session.login(*tokens))


@check_n_args(1)
def join(session: Session, tokens: List[str]) -> str:
    return "join"


@check_n_args(1)
def create(session: Session, tokens: List[str]) -> str:
    return "create"


@check_n_args(2, None)
def say(session: Session, tokens: List[str]) -> str:
    return "say"


@check_n_args()
def channels(session: Session, tokens: List[str]) -> str:
    return "channels"


def handle(session: Session, msg: str) -> str:
    tokens: List[str] = msg.strip().split()

    if not msg:
        return "RESULT ERROR empty message"

    msg_type: str = tokens.pop(0)
    result: str = ""
    if msg_type == "REGISTER":
        result = register(session, tokens)
    elif msg_type == "LOGIN":
        result = login(session, tokens)
    elif msg_type == "JOIN":
        result = join(session, tokens)
    elif msg_type == "CREATE":
        result = create(session, tokens)
    elif msg_type == "SAY":
        result = say(session, tokens)
    elif msg_type == "CHANNELS":
        result = channels(session, tokens)
    else:
        return f"RESULT ERROR unrecognised message type {msg_type}"

    return f"RESULT {result}"


def accept(server: socket.socket) -> Session:
    conn, addr = server.accept()
    logging.info(f"Accept connection from address {addr}")
    conn.setblocking(False)
    session = Session()
    selector.register(conn, selectors.EVENT_READ, session)
    return session


def read(key):
    conn = key.fileobj
    session = key.data
    try:
        msg = conn.recv(1024).decode()
        if msg:
            logging.debug(f"Recieved {msg!r} from {conn.getpeername()}")
            session.pending.append(msg)
            selector.modify(conn, selectors.EVENT_WRITE, key.data)
        else:
            close(key)
    except UnicodeError:
        logging.warning(f"Can not decode message from {conn.getpeername()}")
    except OSError as e:
        logging.warning(f"{type(e).__name__}: {e}")
        session.logout()
        selector.unregister(conn)


def write(key):
    conn = key.fileobj
    session = key.data
    try:
        while session.replies:
            reply: str = session.replies.pop(0) + "\n"
            logging.debug(f"Sending {reply!r} to {conn.getpeername()}")
            conn.send(reply.encode())
        selector.modify(conn, selectors.EVENT_READ, key.data)
    except OSError as e:
        logging.warning(f"{type(e).__name__}: {e}")
        session.logout()
        selector.unregister(conn)


def close(key):
    conn = key.fileobj
    session = key.data
    logging.info(f"Closing connection to {conn.getpeername()}")
    session.logout()
    selector.unregister(conn)
    conn.close()


# Use this variable for your loop
loop = True


# Do not modify or remove this handler
def quit_gracefully(signum, frame):
    global loop
    loop = False
    logging.info("Recieved interrupt signal")


def main():
    signal.signal(signal.SIGINT, quit_gracefully)

    port = int(sys.argv[1])

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setblocking(False)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen()
    selector.register(server, selectors.EVENT_READ, None)

    sessions = []

    while loop:
        events = selector.select(1)
        for key, mask in events:
            if key.data is None:
                sessions.append(accept(server))
            elif mask & selectors.EVENT_READ:
                read(key)
            elif mask & selectors.EVENT_WRITE:
                write(key)

        for session in sessions:
            session.handle()

    logging.info("Closing the server")
    server.close()


if __name__ == "__main__":
    main()
