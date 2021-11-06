#!/bin/python
import hashlib
import logging
import os
import select
import signal
import socket
import sys


def handle(msg):
    return msg


# Use this variable for your loop
loop = True


# Do not modify or remove this handler
def quit_gracefully(signum, frame):
    global loop
    loop = False
    logging.info("Interrupt triggered")


def main():
    """
    The main program setups the server and manages incoming and outgoing
    socket communications. It handles interrupt gracefullly and closes server
    before exiting the program.
    """
    signal.signal(signal.SIGINT, quit_gracefully)

    logging.basicConfig(level=logging.DEBUG)

    port = int(sys.argv[1])

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setblocking(False)
    server.bind(("localhost", port))
    server.listen()
    rlist = [server]
    wlist = []
    session = {}

    while loop:
        readable, writable, exceptional = select.select(rlist, wlist, rlist, 1)
        for s in readable:
            if s is server:
                conn, addr = s.accept()
                conn.setblocking(False)
                rlist.append(conn)
                session[conn] = []
                logging.info(f"Accepted connection from address {addr}")
            else:
                try:
                    data = s.recv(1024)
                    if data:
                        logging.debug(f"Recieved data {data}")
                        session[s].append(data)
                        if s not in wlist:
                            wlist.append(s)
                    else:
                        if s in wlist:
                            wlist.remove(s)
                        if s in writable:
                            writable.remove(s)
                        rlist.remove(s)
                        logging.info(f"Closing connection on {s.getpeername()}")
                        s.close()
                        session.pop(s)
                except OSError as e:
                    logging.warning(e)

        for s in writable:
            try:
                if session[s]:
                    result = handle(session[s].pop())
                    wlist.remove(s)
                    logging.debug(f"Sending {result} to {s.getpeername()}")
                    s.send(result)
            except OSError as e:
                logging.warning(e)
                if s in rlist:
                    rlist.remove(s)
                session.pop(s)

        for s in exceptional:
            logging.info(f"Closing connection on {s.address} with exceptional "
                         "condition")
            rlist.remove(s)
            if s in wlist:
                wlist.remove(s)
            s.close()
            session.pop(s)

    logging.info("Closing the server")
    server.close()


if __name__ == '__main__':
    main()
