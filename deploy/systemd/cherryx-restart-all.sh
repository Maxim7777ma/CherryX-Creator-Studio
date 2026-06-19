#!/usr/bin/env bash
set -euo pipefail

sudo systemctl daemon-reload
sudo systemctl restart cherryx-web.service
sudo systemctl status cherryx-web.service cherryx-bot.service cherryx-worker.service --no-pager
