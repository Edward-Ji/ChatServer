# Chat Server

This is a simple chat server written using Python socket - a low-level network
interface. It can handle multiple client connections at the same time using
Python selectors. To launch the server, use the following command.
```
./server.py <port>
```

## Protocol

Messages both ways are sent in UTF-8 encoding.

### Register

From client to server,
```
REGISTER <username> <password>
```
The server attempts to register a new user with the given name and password. It
fails if a user with that name exists.

---

From server to client,
```
RESULT REGISTER <status>
```
The status is `1` if the registration is successful and `0` otherwise.

### Login

From client to server,
```
LOGIN <username> <password>
```
The server attempts to login the user with the given name using the password. It
fails if one of the following is met:
- The client is already logged in as another user;
- The user is logged in by another client;
- No user with such name exists;
- The password is incorrect.

---

From server to client,
```
RESULT LOGIN <status>
```
The status is `1` if the client is logged in successfully and `0` otherwise.

### Create Channel

From client to server,
```
CREATE <name>
```
The server attempts to create a channel with the given name. It fails if one of
the following is met:
- The client is not logged in;
- A channel with such name exists.

---

From server to client,
```
RESULT CREATE <name> <status>
```
The status is `1` if the channel is successfully created and `0` otherwise.

### Join Channel

From client to server,
```
JOIN <name>
```
The server attempts to join the user to the channel with the given name. It
fails if one of the following is met:
- The client is not logged in;
- A channel with such name does not exists;
- The user has already joined the channel.

---

From server to client,
```
RESULT JOIN <name> <status>
```
The status is `1` if the user successfully joins the channel and `0` otherwise.

### List Channels

From client to server,
```
CHANNELS
```
The server shows a list of all channels.

---

From server to client,
```
RESULT CHANNELS <names>
```
The result is a list of all channel names joined with `, ` (comma and space).

### Send and Receive Messages

From one client to server,
```
SEND <channel> <message>
```
The server attempts to send a message to all users in the specified channel. It
fails if the client is not logged in as a user in that specified channel. If the
message has consecutive white spaces, they are replaced with one space.

---

From server to the sender client, if the server fail to send the message,
```
RESULT SEND ERROR
```

From server to all clients logged in as a user in that specified channel,
```
RECV <username> <channel> <message>
```
The name is that of the user who sent the message. It is followed by the channel
name in which the message is sent and the message.

### Error Message

Except for the status message specified for each command. If the message from a
client to the server has incorrect number of arguments, the server will send
back
```
RESULT ERROR not enough arguments
```
or
```
RESULT ERROR too many arguments
```

If the client sends a message starting with an unknown type, the server will
send back
```
RESULT ERROR unknown type
```

## Client

After starting a local server at port 5050 (or any other vacant port). You can
use `netcat` or `client.py` to communicate with the server.
```
netcat localhost 5050
```
or
```
python3 client.py 5050
```

## Testing

### Simple I/O Tests

Run all tests directly by running `testing.py`.
```
python3 testing.py [<pattern>]
```

If a pattern is specified, only test cases with the pattern in its name is run.

The script automatically runs all test cases in the `testing` directory. It sets
up all the servers at localhost. It uses custom client objects to check sent and
received messages. The test case fails if the client fails to send specified
message in the test case or the received message mismatch the expected one. It
also fails upon an unhandled exception.

After running each test, the script prints to standard out if the test passed or
failed. It also writes a full record to `testing.json` after all tests are run.

The script returns with a non-zero status if any test case fails.

### Test Syntax

This section explains the syntax of the test cases in the `testing` directory.

```
<name> <action> [<argument>...] [# <comment>]
```
The available actions are:
- `@` followed by an integer port number. This command starts up a server
  process at the specified port;
- `~` followed by the name of a previously set up server. This command sets up a
  client socket to connect to that server's port;
- `>` followed by a series of words. This command sends the words through the
  client. If it fails to send the message, the test fails.
- `<` followed by a series of words. This command tells the client to receive
  data and compares it with the specified words. If they do not match, the test
  fails.
- `!` This command closes the client socket.

Empty lines and comments are ignored.

### Coverage

To run all tests with coverage on `server.py`,

```
./testcov
```

It accomplishes the following:
- Run `testing.py` and generate a series of coverage data. This includes all
  functions described in Simple I/O Tests;
- Combine the coverage data from multiple server processes;
- Display a brief coverage report;
- Generate a detailed html report at `htmlcov/index.html`.
