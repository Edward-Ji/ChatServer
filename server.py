#!/usr/bin/env python3
import logging
import os
import selectors
import signal
import socket
import sys

from hashlib import pbkdf2_hmac
from typing import Callable, List, Optional


# Initialize a logger at debug level, but defaults to disabled.
logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.disabled = True

# Initialize a selector for non-blocking socket I/O.
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
        self.logged_in: Optional[Session] = None
        self.instances.append(self)

    @classmethod
    def by_name(cls, name: str) -> Optional["User"]:
        for user in cls.instances:
            if user.name == name:
                return user

    @classmethod
    def register(cls, name: str, passwd: str) -> bool:
        if cls.by_name(name) is not None:
            return False
        cls(name, passwd)
        return True

    def login(self, session: "Session", passwd: str) -> bool:
        if self.logged_in is not None:
            return False
        passhash: bytes = pbkdf2_hmac("sha256",
                                      passwd.encode(),
                                      self._salt,
                                      1000)
        if self._passhash == passhash:
            self.logged_in = session
            return True
        else:
            return False

    def logout(self):
        self.logged_in = None

    def join(self, channel_name: str) -> bool:
        channel = Channel.by_name(channel_name)
        if channel is None:
            return False
        return channel.add_user(self)

    def say(self, channel_name: str, *words: str) -> bool:
        channel = Channel.by_name(channel_name)
        if channel is None or self not in channel.users:
            return False
        channel.broadcast(self, *words)
        return True


class Channel:

    instances: List["Channel"] = []

    def __init__(self, name: str):
        self.name = name
        self.users: List[User] = []
        self.instances.append(self)

    def add_user(self, user: User) -> bool:
        if user in self.users:
            return False
        self.users.append(user)
        return True

    def broadcast(self, user: User, *words: str) -> None:
        words = " ".join(words)
        msg = f"RECV {user.name} {self.name} {words}"
        for user in self.users:
            user.logged_in.replies.append(msg)

    @classmethod
    def by_name(cls, name: str) -> Optional["Channel"]:
        for channel in cls.instances:
            if channel.name == name:
                return channel

    @classmethod
    def create(cls, name: str) -> bool:
        if cls.by_name(name) is not None:
            return False
        cls(name)
        return True


class Session:

    def __init__(self):
        self.user: User = None
        self.pending: List[str] = []
        self.replies: List[str] = []

    def login(self, name: str, passwd: str) -> bool:
        if self.user is not None:
            return False
        for user in User.instances:
            if user.name == name:
                if user.login(self, passwd):
                    self.user = user
                    return True
                break
        return False

    def logout(self):
        if self.user is not None:
            self.user.logout()

    def handle(self):
        while self.pending:
            result = handle(self, self.pending.pop(0))
            if result is not None:
                self.replies.append(result)


def check_n_args(*limit: int) -> Callable:
    min_limit: int
    max_limit: int
    if len(limit) == 1:
        min_limit, = max_limit, = limit
    else:
        min_limit, max_limit = limit

    def decorator(func: Callable) -> Callable:
        def wrapper(session: Session, tokens: List[str]) -> str:
            if len(tokens) < min_limit:
                return "ERROR not enough arguments"
            if max_limit != -1 and len(tokens) > max_limit:
                return "ERROR too many arguments"
            return func(session, tokens)
        return wrapper
    return decorator


@check_n_args(2)
def register(session: Session, tokens: List[str]) -> str:
    status: bool = User.register(*tokens)
    return "{:d}".format(status)


@check_n_args(2)
def login(session: Session, tokens: List[str]) -> str:
    status: bool = session.login(*tokens)
    return "{:d}".format(status)


@check_n_args(1)
def join(session: Session, tokens: List[str]) -> str:
    if session.user is None:
        status: bool = False
    else:
        status: bool = session.user.join(*tokens)
    return "{} {:d}".format(tokens[0], status)


@check_n_args(1)
def create(session: Session, tokens: List[str]) -> str:
    if session.user is None:
        status: bool = False
    else:
        status: bool = Channel.create(*tokens)
    return "{} {:d}".format(tokens[0], status)


@check_n_args(2, -1)
def say(session: Session, tokens: List[str]) -> Optional[str]:
    if session.user is None or not session.user.say(*tokens):
        return "0"


@check_n_args(0)
def channels(session: Session, tokens: List[str]) -> str:
    # Return a sorted list of all channel names, joined by comma space.
    return ", ".join(sorted(map(lambda c: c.name, Channel.instances)))


def handle(session: Session, msg: str) -> Optional[str]:
    tokens: List[str] = msg.strip().split()

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
        return "RESULT ERROR unknown message type"

    if result is not None:
        return f"RESULT {msg_type} {result}"


def accept(server: socket.socket) -> Session:
    conn, addr = server.accept()
    logger.info(f"Accept connection from address {addr}")
    conn.setblocking(False)
    session = Session()
    selector.register(conn,
                      selectors.EVENT_READ | selectors.EVENT_WRITE,
                      session)
    return session


def read(key):
    conn = key.fileobj
    session = key.data
    try:
        msg = conn.recv(1024).decode()
        if msg:
            logger.debug(f"Received {msg!r} from {conn.getpeername()}")
            session.pending.extend(filter(None, msg.split("\n")))
        else:
            close(key)
    except UnicodeError:
        logger.warning(f"Can not decode message from {conn.getpeername()}")
    except OSError as e:
        logger.warning(f"{type(e).__name__}: {e}")
        session.logout()
        selector.unregister(conn)


def write(key):
    conn = key.fileobj
    session = key.data
    try:
        while session.replies:
            reply: str = session.replies.pop(0) + "\n"
            logger.debug(f"Sending {reply!r} to {conn.getpeername()}")
            conn.send(reply.encode())
    except OSError as e:
        logger.warning(f"{type(e).__name__}: {e}")
        session.logout()
        selector.unregister(conn)


def close(key):
    conn = key.fileobj
    session = key.data
    logger.info(f"Closing connection to {conn.getpeername()}")
    session.logout()
    selector.unregister(conn)
    conn.close()


# Use this variable for your loop
loop = True


# Do not modify or remove this handler
def quit_gracefully(signum, frame):
    global loop
    logger.info("Received interrupt signal")
    loop = False


def server(port):
    signal.signal(signal.SIGINT, quit_gracefully)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setblocking(False)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen()
    selector.register(server, selectors.EVENT_READ, None)
    logger.info(f"Server start listening port {port}")

    sessions = []

    while loop:
        events = selector.select(1)
        for key, mask in events:
            if key.data is None:
                sessions.append(accept(server))
            else:
                if mask & selectors.EVENT_READ:
                    read(key)
                if mask & selectors.EVENT_WRITE:
                    write(key)

        for session in sessions:
            session.handle()

    logger.info("Closing the server")
    server.close()
    selector.close()


def main():
    # Enable the logger if run as main program.
    logger.disabled = False
    server(int(sys.argv[1]))


if __name__ == "__main__":
    main()
