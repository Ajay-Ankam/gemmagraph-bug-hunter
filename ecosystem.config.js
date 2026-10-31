// PM2 process definition for GemmaGraph Bug Hunter on Cloudways.
//
// PM2 supervises Uvicorn (auto-restart, log rotation, boot persistence).
// Python can't use PM2's Node "cluster" mode, so parallelism comes from
// Uvicorn's own --workers; all workers share backend/.scan_cache.json.
//
//   pm2 startOrReload ecosystem.config.js && pm2 save
const path = require("path");

const ROOT = __dirname;
const PORT = process.env.PORT || "8000";
const WORKERS = process.env.WEB_CONCURRENCY || "2";

module.exports = {
  apps: [
    {
      name: "gemmagraph",
      cwd: path.join(ROOT, "backend"),
      script: path.join(ROOT, ".venv", "bin", "uvicorn"),
      interpreter: "none",
      args: [
        "main:app",
        "--host", "127.0.0.1", // only reachable through the Cloudways proxy, never directly
        "--port", PORT,
        "--workers", WORKERS,
        "--proxy-headers",
        "--forwarded-allow-ips", "127.0.0.1",
        "--timeout-keep-alive", "30",
      ],
      env: {
        PYTHONUNBUFFERED: "1",
        LOG_LEVEL: "INFO",
        MAX_LIVE_SCANS: "2",
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      max_memory_restart: "800M",
      kill_timeout: 10000,
      out_file: path.join(ROOT, "logs", "gemmagraph.out.log"),
      error_file: path.join(ROOT, "logs", "gemmagraph.err.log"),
      time: true,
    },
  ],
};
