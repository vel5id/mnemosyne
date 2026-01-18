#!/bin/bash
# Mnemosyne LLM Container - Auto-pull models on startup

# Start Ollama server in background
/bin/ollama serve &
pid=$!

echo "Waiting for Ollama LLM server..."
sleep 5
while ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "Ollama LLM server started!"

# Check if model already exists
if ollama list | grep -q "deepseek-r1"; then
    echo "Model deepseek-r1:1.5b already loaded"
else
    echo "Pulling deepseek-r1:1.5b model..."
    ollama pull deepseek-r1:1.5b
    echo "Model deepseek-r1:1.5b ready!"
fi

# Keep server running
wait $pid
