import http.server
import threading
import logging
from pg_controller import state


class ManagementRequestHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/controller/ready":
            response_code = 200 if state.INSTANCE.is_ready else 503
            self._respond(response_code, state.INSTANCE.is_ready)
        elif self.path == "/controller/role":
            self._respond(200, state.INSTANCE.role)
        else:
            self._respond(404, "Endpoint not found!")

    def _respond(self, response_code, body):
        self.send_response(response_code)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(str(body).encode("utf-8"))

    def log_message(self, msg_format, *args):
        logging.info(msg_format % args)


class ManagementServer(threading.Thread):

    def __init__(self, port):
        super().__init__(name=self.__class__.__name__)
        self._port = port
        self._server = http.server.HTTPServer(("", self._port), ManagementRequestHandler)

    def run(self):
        self._server.serve_forever()
        logging.info("Stopped!")

    def stop(self):
        logging.info("Stopping management server ...")
        self._server.shutdown()
