import selectors
import socket
import sys


selector: selectors.BaseSelector = selectors.DefaultSelector()


def main():
    server_port = int(sys.argv[1])

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("localhost", server_port))
    client.setblocking(False)
    selector.register(client, selectors.EVENT_READ)

    selector.register(sys.stdin, selectors.EVENT_READ)

    try:
        while True:
            events = selector.select(1)
            for key, mask in events:
                if key.fileobj is sys.stdin:
                    line = sys.stdin.readline()
                    client.send(line.encode())
                if key.fileobj is client:
                    sys.stdout.write(client.recv(1024).decode())
    except KeyboardInterrupt:
        pass
    else:
        client.close()


if __name__ == '__main__':
    main()
