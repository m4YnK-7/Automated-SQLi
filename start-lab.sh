set -e
echo "[*] Building & starting lab (docker compose)..."
docker compose up --build -d
echo "[*] Lab started. Access DVWA at http://localhost:8080"
echo "[*] Logs are written to ./logs/traces.jl"