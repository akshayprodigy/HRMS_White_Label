import multiprocessing
import os

# Gunicorn configuration for production
bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
loglevel = os.getenv("LOG_LEVEL", "info")
# Use a higher timeout for potentially slow queries or operations
timeout = 120
keepalive = 2
# Forwarded Allow IPS - trust the reverse proxy (Nginx)
forwarded_allow_ips = "*"
# Access log set to stdout for Docker logging
accesslog = "-"
errorlog = "-"
