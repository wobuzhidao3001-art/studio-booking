#!/bin/bash
set -e
cd ~/studio-booking
echo "=== Stopping old ==="
docker compose down 2>/dev/null || true
echo "=== Building ==="
docker compose build --no-cache
echo "=== Starting ==="
docker compose up -d
sleep 3
echo "=== Status ==="
docker compose ps
echo "=== Logs ==="
docker compose logs --tail=20
echo "=== Done ==="
