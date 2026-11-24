#!/bin/bash
# For 32-bit Raspberry Pi OS (where Ollama doesn't work): builds llama.cpp, downloads a small chat model,
# and runs it in the background on port 8099 for the chatbot. Takes 30-60 minutes (most of it is building).
set -e
sudo apt update
sudo apt install -y git cmake build-essential wget
[ -d "$HOME/llama.cpp" ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$HOME/llama.cpp"
cd "$HOME/llama.cpp"
cmake -B build -DLLAMA_CURL=OFF
cmake --build build --config Release -j4 --target llama-server
mkdir -p "$HOME/models"
MODEL="$HOME/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"
wget -c -O "$MODEL" https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf

sudo tee /etc/systemd/system/llamaserver.service > /dev/null << SERVICE
[Unit]
Description=llama.cpp chat model for Pi Self-Learning AI
After=network.target

[Service]
User=$USER
ExecStart=$HOME/llama.cpp/build/bin/llama-server -m $MODEL --host 127.0.0.1 --port 8099 -t 4 -c 2048
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE
sudo systemctl daemon-reload
sudo systemctl enable --now llamaserver
echo
echo "Done! The chat model is starting on port 8099 (give it a minute to load)."
echo "Check it:  curl http://127.0.0.1:8099/health"
