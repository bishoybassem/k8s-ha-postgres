import http.server
import threading
import logging
from pg_controller import state


class ManagementRequestHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/controller/ready":
            response_code = 503 if state.INSTANCE.initializing else 200
            self.send_response(response_code)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            body = str(not state.INSTANCE.initializing).encode("utf-8")
            self.wfile.write(body)
        elif self.path == "/controller/role":
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            body = str(state.INSTANCE.role).encode("utf-8")
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

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
