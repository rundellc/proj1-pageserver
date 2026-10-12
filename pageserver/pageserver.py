"""
  A trivial web server in Python.

  Based largely on https://docs.python.org/3.4/howto/sockets.html
  This trivial implementation is not robust:  We have omitted decent
  error handling and many other things to keep the illustration as simple
  as possible.

  FIXME:
  Currently this program always serves an ascii graphic of a cat.
  Change it to serve files if they end with .html or .css, and are
  located in ./pages  (where '.' is the directory from which this
  program is run).
"""
import os       # For checking existence of DOCROOT
import config    # Configure from .ini files and command line
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
docroot = os.path.join(PROJECT_ROOT, config.configuration().DOCROOT)


import logging   # Better than print statements
logging.basicConfig(format='%(levelname)s:%(message)s',
                    level=logging.INFO)
log = logging.getLogger(__name__)
# Logging level may be overridden by configuration 

import socket    # Basic TCP/IP communication on the internet
import _thread   # Response computation runs concurrently with main program


def listen(portnum):
    """
    Create and listen to a server socket.
    Args:
       portnum: Integer in range 1024-65535; temporary use ports
           should be in range 49152-65535.
    Returns:
       A server socket, unless connection fails (e.g., because
       the port is already in use).
    """
    # Internet, streaming socket
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Bind to port and make accessible from anywhere that has our IP address
        serversocket.bind(('', portnum))
        log.info("Binding socket to port {}".format(portnum))
        serversocket.listen(1)    # A real server would have multiple listeners
        log.info("Server is now listening on port {}".format(portnum))
        return serversocket
    
    except Exception as e:
        log.error("Failed to bind or listen on port {}: {}".format(portnum, e))
        serversocket.close()
        return None


def serve(sock, func):
    """
    Respond to connections on sock.
    Args:
       sock:  A server socket, already listening on some port.
       func:  a function that takes a client socket and does something with it
    Returns: nothing
    Effects:
        For each connection, func is called on a client socket connected
        to the connected client, running concurrently in its own thread.
    """

    while True:
        try: # try for accepting a new client connection
            (clientsocket, address) = sock.accept() # accept a new client connection with try, except for os errors
            log.info("Accepted connection from {}".format(address))

        # lazy handling of accept failures
        except Exception as e:
            log.error("Failed to accept a connection: {}".format(e))
            continue

        # another try block for starting a new thread
        try:
            _thread.start_new_thread(func, (clientsocket,)) # start a new thread for the client connection
            log.info("Started a new thread for connection from {}".format(address))

        # lazy handling of thread start failures
        except Exception as e:
            log.error("Failed to start a new thread for connection from {}: {}".format(address, e))

##
# Starter version only serves cat pictures. In fact, only a
# particular cat picture. This one.
##
CAT = """
     ^ ^
   =(   )=
"""

# HTTP response codes, as the strings we will actually send.
# See:  https://en.wikipedia.org/wiki/List_of_HTTP_status_codes
# or    http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html
##
STATUS_OK = "HTTP/1.0 200 OK\nContent-Type: {content_type}\nContent-Length: {content_length}\n\n"
STATUS_MALFORMED_REQUEST = "HTTP/1.0 400 Bad Request\n\n"
STATUS_FORBIDDEN = "HTTP/1.0 403 Forbidden\n\n"
STATUS_NOT_FOUND = "HTTP/1.0 404 Not Found\n\n"
STATUS_INTERNAL_SERVER_ERROR = "HTTP/1.0 500 Internal Server Error\n\n"
STATUS_NOT_IMPLEMENTED = "HTTP/1.0 501 Not Implemented\n\n"

def shutdown_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception as e:
        log.error("Failed to shutdown socket: {}".format(e))
    finally:
        sock.close()

def respond(sock):
    """
    This server responds only to GET requests (not PUT, POST, or UPDATE).
    Any valid GET request is answered with an ascii graphic of a cat.
    """
    ##########
    # Request Receiving
    ##########
    request = sock.recv(1024)  # We accept only short requests, i.e., requests that fit within 1024 bytes
    request = str(request, encoding='utf-8', errors='strict') # decode the request from bytes to string
    log.info("--- Received request ----")

    
    parts = request.split() # split the request into its components (method, everything else)
    if len(parts) < 2: # cant process requests with fewer than 2 parts (method and path)
        log.info("Malformed request: {}".format(request))

        transmit(STATUS_MALFORMED_REQUEST, sock) # inform the client that the request is bad form

        shutdown_socket(sock) # shutdown and close the socket early cause bad request is a bad request
        return 0

    request_type = parts[0]
    path = parts[1]


    log.info("Received request: {} with path: {} from client {}".format(request_type, path, sock.getpeername()))
    log.info("Request type: {} Path: {}".format(request_type, path))
    ##########

    ##########
    # Immediate Response Path Validation
    ##########
    if not path.startswith("/"):
        log.info("Path does not start with a '/', aborting with malformed request")
        transmit(STATUS_MALFORMED_REQUEST, sock)
        shutdown_socket(sock)
        return

    elif ".." in path or "/~" in path or "//" in path:
        log.info("Path is forbidden: {}".format(path))
        transmit(STATUS_FORBIDDEN, sock)
        shutdown_socket(sock)
        return

    else:
        log.info("Request path passed immediate validation checks")
    

    ##########
    #Document Root Validation
    ##########

    log.info("Document root resolved to: {}".format(docroot))

    if not os.path.isdir(docroot):
        log.error("NEEDS FIX: The configured DOCROOT in app.ini does not exist: {}".format(docroot))

        message = "We messed up! Our file structure has changed or moved somewhere else.\n"
        transmit(STATUS_INTERNAL_SERVER_ERROR, sock)
        transmit(message, sock)
        shutdown_socket(sock) # shutdown and close the socket after sending the error message
        return 0

    else:
        log.info("Root directory for pages exists: {}".format(docroot))

    ##########

    if request_type != "GET":
        log.info("Request type received is not GET ({}), aborting with forbidden status".format(request_type))
        transmit(STATUS_FORBIDDEN, sock)
        transmit(CAT, sock)
        shutdown_socket(sock)
        return

    else:
        log.info("Request type is GET, proceeding with request handling")

        real_root = os.path.realpath(docroot) # resolve the absolute path of the document root
        real_file = os.path.realpath(os.path.join(docroot, path.lstrip("/"))) # resolve the absolute path of the requested file

        file_extension = os.path.splitext(real_file)[1] # get the file extension of the requested file
        if file_extension not in [".html", ".css"]: # check if the file extension is allowed
            transmit(STATUS_FORBIDDEN, sock) # send a forbidden status if the file type is not allowed
            shutdown_socket(sock)
            return

        if not real_file.startswith(real_root + os.sep): # check if the requested file is within the document root
            transmit(STATUS_FORBIDDEN, sock) # send them out the door if not
            shutdown_socket(sock)
            return

        if not os.path.isfile(real_file): # check if the requested file actually exists
            transmit(STATUS_NOT_FOUND, sock) # send a not found status if it doesn't
            shutdown_socket(sock)
            return

        # it's a file under root, serve it
        content_type = "text/html" if file_extension == ".html" else "text/css"
        
        with open(real_file, "rb") as f:
            body = f.read()
            log.info("Read {} bytes from file {}".format(len(body), real_file))

        header = STATUS_OK.format(content_type=content_type, content_length=len(body))
        transmit(header, sock)
        sock.sendall(body)
        shutdown_socket(sock) # close the connection after serving the file


def transmit(msg, sock):
    """It might take several sends to get the whole message out"""

    data = msg.encode("utf-8") # encode the message to bytes
    data_length = len(data) # total length of the data to be sent
    total_sent = 0

    buff_max = 1024 # size of the buffer for each send operation

    while total_sent < data_length: # continue sending until all data is sent

        if total_sent + buff_max > data_length: # adjust the buffer size for the last chunk
            buff_max = data_length - total_sent # remaining bytes to send, adjusts the buffer so it can send 1024 bytes while ensuring it does not exceed the data length

        buff = data[total_sent:total_sent+buff_max] # get the next chunk of data to send, ensurse it does not exceed the remaining data length
        sent = sock.send(buff) # send the chunk and update the total sent
        total_sent += sent
        log.debug("Sent {} of {} bytes to client".format(total_sent, data_length))
        if sent == 0:
            raise ConnectionError("client disconnected during send")

    log.info("Sent {} bytes to client".format(total_sent))

    return total_sent

###
#
# Run from command line
#
###


def get_options():
    """
    Options from command line or configuration file.
    Returns namespace object with option value for port
    """
    # Defaults from configuration files;
    #   on conflict, the last value read has precedence
    options = config.configuration()
    # We want: PORT, DOCROOT, possibly LOGGING

    if options.PORT <= 1000:
        log.warning(("Port {} selected. " +
                         " Ports 0..1000 are reserved \n" +
                         "by the operating system").format(options.port))

    return options


def main():
    options = get_options()
    port = options.PORT
    if options.DEBUG:
        log.setLevel(logging.DEBUG)

    sock = None
    try:
        sock = listen(port)
        if sock is None:
            return
        log.info("Listening on port {}".format(port))
        log.info("Socket is {}".format(sock))
        serve(sock, respond)

    except Exception as e:
        log.error("An error occurred: {}".format(e))

    finally:
        if sock is not None:
            shutdown_socket(sock)

if __name__ == "__main__":
    main()
