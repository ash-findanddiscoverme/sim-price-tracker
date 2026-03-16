import http.server
import socketserver
import os
import sys

os.chdir(sys.argv[1])

class IPv4Server(socketserver.TCPServer):
    allow_reuse_address = True
    address_family = __import__('socket').AF_INET

handler = http.server.SimpleHTTPRequestHandler
port = int(sys.argv[2])

print(f'Serving on port {port}')
with IPv4Server(('', port), handler) as httpd:
    httpd.serve_forever()
