#!/bin/bash
# Mnemosyne VLM Container - Auto-pull models on startup

# Start Ollama server in background
/bin/ollama serve &
pid=$!

echo "Waiting for Ollama VLM server..."
sleep 5
while ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "Ollama VLM server started!"

# Check if model already exists
if ollama list | grep -q "minicpm-v"; then
    echo "Model minicpm-v already loaded"
else
    echo "Pulling minicpm-v model..."
    ollama pull minicpm-v
    echo "Model minicpm-v ready!"
fi

# Keep server running
wait $pid
