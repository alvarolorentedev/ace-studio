import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ace_studio.api import AceClient
from ace_studio.models import GenerationRequest


class Handler(BaseHTTPRequestHandler):
    authorization = ""
    body = b""
    release_body = b""

    def log_message(self, *_args):
        pass

    def _reply(self, data):
        payload = json.dumps({"code": 200, "data": data}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        type(self).authorization = self.headers.get("Authorization", "")
        if self.path.startswith("/v1/audio"):
            payload = b"RIFFaudio"
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self._reply({"status": "Idle"})

    def do_POST(self):
        type(self).authorization = self.headers.get("Authorization", "")
        length = int(self.headers.get("Content-Length", 0))
        type(self).body = self.rfile.read(length)
        if self.path == "/release_task":
            type(self).release_body = type(self).body
            self._reply({"task_id": "one"})
        elif self.path == "/query_result":
            self._reply([{"status": 1, "result": [{"file": "/v1/audio?path=one.wav"}]}])
        else:
            self._reply({"message": "ok"})


class HttpIntegrationTest(unittest.TestCase):
    def test_authenticated_multipart_poll_and_download(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = AceClient(server.server_port, "secret")
            task_id = client.generate(GenerationRequest("ambient"))
            result = client.wait(task_id, poll_interval=0)
            with tempfile.TemporaryDirectory() as directory:
                target = client.download_audio(result.audio_paths[0], Path(directory) / "one.wav")
                self.assertEqual(target.read_bytes(), b"RIFFaudio")
            self.assertEqual(Handler.authorization, "Bearer secret")
            self.assertIn(b'name="prompt"', Handler.release_body)
            self.assertEqual(client.training_status()["status"], "Idle")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
