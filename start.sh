#!/bin/bash
# Bio Link Protector Bot - 24/7 daemon with auto-restart

echo "Starting Bio Link Protector Bot..."

while true; do
    python3 bot.py
    echo "Bot stopped unexpectedly. Restarting in 5 seconds..."
    sleep 5
done
