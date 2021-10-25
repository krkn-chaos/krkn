import sys
import logging
import _thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from http.client import HTTPConnection


# Start a simple http server to publish the cerberus status file content
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    requests_served = 0

    def do_GET(self):
        if self.path == "/":
            self.do_status()

    def do_status(self):
        self.send_response(200)
        self.end_headers()
        f = open("/tmp/kraken_status", "rb")
        self.wfile.write(f.read())
        SimpleHTTPRequestHandler.requests_served = SimpleHTTPRequestHandler.requests_served + 1

    def do_POST(self):
        if self.path == "/STOP":
            self.set_stop()
        elif self.path == "/RUN":
            self.set_run()
        elif self.path == "/PAUSE":
            self.set_pause()

    def set_run(self):
        self.send_response(200)
        self.end_headers()
        with open("/tmp/kraken_status", "w+") as file:
            file.write(str("RUN"))

    def set_stop(self):
        self.send_response(200)
        self.end_headers()
        with open("/tmp/kraken_status", "w+") as file:
            file.write(str("STOP"))

    def set_pause(self):
        self.send_response(200)
        self.end_headers()
        with open("/tmp/kraken_status", "w+") as file:
            file.write(str("PAUSE"))


def start_server(address):
    server = address[0]
    port = address[1]
    global httpd
    httpd = HTTPServer(address, SimpleHTTPRequestHandler)
    logging.info("Starting http server at http://%s:%s\n" % (server, port))
    try:
        _thread.start_new_thread(httpd.serve_forever, ())
    except Exception:
        logging.error(
            "Failed to start the http server \
                      at http://%s:%s"
            % (server, port)
        )
        sys.exit(1)


def get_status(address):
    server = address[0]
    port = address[1]
    httpc = HTTPConnection(server, port)
    logging.info("connection set up")
    httpc.request("GET", "/")
    response = httpc.getresponse()
    status = response.read()
    logging.info("response " + str(status.decode()))
    return status.decode()
