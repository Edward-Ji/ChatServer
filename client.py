import selectors
import socket
import sys


selector: selectors.BaseSelector = selectors.DefaultSelector()


def main():
    server_port = int(sys.argv[1])

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("localhost", server_port))
    client.setblocking(False)
    selector.register(client, selectors.EVENT_READ | selectors.EVENT_WRITE)

    selector.register(sys.stdin, selectors.EVENT_READ)

    pending = []

    try:
        while True:
            events = selector.select(1)
            for key, mask in events:
                if key.fileobj is sys.stdin:
                    pending.append(sys.stdin.readline())
                if key.fileobj is client:
                    if mask & selectors.EVENT_READ:
                        sys.stdout.write(client.recv(1024).decode())
                    if mask & selectors.EVENT_WRITE:
                        while pending:
                            client.send(pending.pop(0).encode())
    except KeyboardInterrupt:
        client.close()
    except Exception as e:
        sys.stdout.write(f"{type(e).__name__}: {e}\n")


if __name__ == '__main__':
    main()
