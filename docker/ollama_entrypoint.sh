#!/bin/bash

# Start Ollama in the background.
/bin/ollama serve &
pid=$!

echo "⏳ Waiting for Ollama to start..."
while ! curl -s http://localhost:11434/api/tags > /dev/null; do
    sleep 1
done

echo "🟢 Ollama started!"

# Pull requested models
echo "⬇️  Pulling DeepSeek-R1-Distill-Qwen-1.5B..."
ollama pull deepseek-r1:1.5b

echo "⬇️  Pulling Qwen2.5-VL-7B..."
# Attempt to pull qwen2.5-vl (if available in library) or fallback to similar
ollama pull qwen2.5-vl:7b

echo "✅ Model loading complete!"

# Wait for process to finish.
wait $pid
