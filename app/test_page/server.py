# Simple static server for the test page
import http.server, socketserver, os

PORT = 8000
ROOT = os.path.dirname(__file__)

os.chdir(ROOT)
with socketserver.TCPServer(("", PORT), http.server.SimpleHTTPRequestHandler) as httpd:
    print(f"Serving test page at http://localhost:{PORT}/login.html")
    httpd.serve_forever()
