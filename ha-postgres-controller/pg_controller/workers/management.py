import http.server
import logging
import socketserver
import threading

from pg_controller import state


class ManagementRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handles management API HTTP requests."""

    def do_GET(self):
        """
        Responds with the database role for 'GET /controller/role' requests, the database readiness for
        'GET controller/ready' requests, otherwise, 404.
        """
        if self.path == "/controller/ready":
            response_code = 200 if state.INSTANCE.is_ready else 503
            self._respond(response_code)
        elif self.path == "/controller/role":
            self._respond(200, state.INSTANCE.role)
        else:
            self._respond(404, "Endpoint not found!")

    def _respond(self, response_code, body=None):
        self.send_response(response_code)
        if body:
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(str(body).encode("utf-8"))
        else:
            self.end_headers()

    def log_message(self, msg_format, *args):
        threading.current_thread().name = 'ManagementServer'
        logging.info(msg_format % args)


class MultiThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Handle each request in a separate thread."""


class ManagementServer(threading.Thread):
    """Exposes the management HTTP API over a specific port."""

    def __init__(self, port):
        """
        :param port: The port to listen to for API requests.
        """
        super().__init__(name=self.__class__.__name__)
        self._port = port
        self._server = MultiThreadedHTTPServer(("", self._port), ManagementRequestHandler)

    def run(self):
        self._server.serve_forever()
        logging.info("Stopped!")

    def stop(self):
        logging.info("Stopping management server ...")
        self._server.shutdown()
