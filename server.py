import sys
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from http.client import HTTPConnection

server_status = ""
status_lock = threading.Lock()
requests_served_lock = threading.Lock()

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    A simple http server to publish the cerberus status file content
    """

    requests_served = 0

    def do_GET(self):
        if self.path == "/":
            self.do_status()

    def do_status(self):
        self.send_response(200)
        self.end_headers()
        with status_lock:
            self.wfile.write(bytes(server_status, encoding='utf8'))
        with requests_served_lock:
            SimpleHTTPRequestHandler.requests_served += 1

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
        publish_kraken_status('RUN')

    def set_stop(self):
        self.send_response(200)
        self.end_headers()
        publish_kraken_status('STOP')

    def set_pause(self):
        self.send_response(200)
        self.end_headers()
        publish_kraken_status('PAUSE')

def publish_kraken_status(status):
    global server_status
    with status_lock:
        server_status = status

def start_server(address, status):
    server = address[0]
    port = address[1]
    global httpd
    httpd = HTTPServer(address, SimpleHTTPRequestHandler)
    logging.info("Starting http server at http://%s:%s" % (server, port))
    try:
        t = threading.Thread(target=httpd.serve_forever)
        t.daemon = True
        t.start()
        publish_kraken_status(status)
    except Exception as e:
        logging.error(f"Failed to start the http server at http://{server}:{port}: {e}")
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
