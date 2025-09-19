# Gunicorn configuration for Pixfy
import multiprocessing
import os

# Server socket
bind = "127.0.0.1:8001"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 60
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "/root/pixfy/logs/gunicorn_access.log"
errorlog = "/root/pixfy/logs/gunicorn_error.log"
loglevel = "info"

# Process naming
proc_name = 'pixfy_gunicorn'

# Server mechanics  
daemon = False
pidfile = "/root/pixfy/gunicorn.pid"
user = "www-data"
group = "www-data"
tmp_upload_dir = None

# Application  
chdir = "/root/pixfy"
wsgi_module = "photobank.wsgi:application"
