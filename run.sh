#!/bin/bash
# run.sh — starts the AI content scheduler in the background

cd /Users/pvsheram/ai-content-system

echo "Starting AI Content System..."
python3 main.py --timezone Asia/Kolkata >> logs/scheduler.log 2>&1
