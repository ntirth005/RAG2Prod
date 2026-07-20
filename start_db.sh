#!/bin/bash
set -e

echo "=== 1. Starting Postgres with pgvector container ==="
if [ "$(sudo docker ps -aq -f name=pgvector)" ]; then
    echo "Container 'pgvector' already exists."
    if [ "$(sudo docker ps -q -f name=pgvector)" ]; then
        echo "Container 'pgvector' is already running."
    else
        echo "Starting existing 'pgvector' container..."
        sudo docker start pgvector
    fi
else
    echo "Creating and starting new 'pgvector' container..."
    sudo docker run --name pgvector \
      -p 5432:5432 \
      -e POSTGRES_DB=rag2prod \
      -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=postgres \
      -d pgvector/pgvector:pg16
fi

echo ""
echo "=== 2. Verifying database connection ==="
# Wait a bit for postgres to startup
sleep 3
# Run a quick check inside the container to see if postgres is ready
sudo docker exec pgvector pg_isready -U postgres

echo ""
echo "=== 3. Showing the last development changes (Git Log) ==="
git log -n 1 --stat

echo ""
echo "=== Setup complete ==="
