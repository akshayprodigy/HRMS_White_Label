#!/bin/sh
set -e

# Wait briefly for MariaDB to accept TCP connections.
python -c "import socket, time
host='db'
port=3306
deadline=time.time()+60
while True:
    try:
        s=socket.create_connection((host, port), timeout=2)
        s.close()
        break
    except OSError:
        if time.time() > deadline:
            raise
        time.sleep(1)
print('DB is reachable')
"

python -m alembic upgrade head

exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
