#!/bin/bash
# For 32-bit Raspberry Pi OS (where Ollama can't run): builds llama.cpp, downloads a small chat model,
# and runs it in the background on port 8099 for the chatbot.
# Takes 45-90 minutes on a Pi 4, almost all of it building. Tip: pause the Docking AI first
# (sudo systemctl stop dockingai), so the build has all the memory and processor it needs.
set -e
LLAMA_VERSION=5fddd0b99888a90260736e0f734fa8e160064e03      # the exact version that was tested
sudo apt update
sudo apt install -y git cmake build-essential wget

if [ ! -x "$HOME/llama.cpp/build/bin/llama-server" ]; then
  rm -rf "$HOME/llama.cpp"
  mkdir -p "$HOME/llama.cpp" && cd "$HOME/llama.cpp"
  git init -q
  git remote add origin https://github.com/ggml-org/llama.cpp
  git fetch -q --depth 1 origin $LLAMA_VERSION
  git checkout -q FETCH_HEAD
  # Build it as a 32-bit program. (On a Pi with a 64-bit kernel and 32-bit programs, it would otherwise
  # think it's 64-bit and fail.) These flags turn on the Pi 4's fast NEON math instructions.
  FLAGS="-mcpu=cortex-a72 -mfpu=neon-fp-armv8 -mfloat-abi=hard"
  cmake -B build -DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=armv7l -DGGML_NATIVE=OFF \
        -DLLAMA_OPENSSL=OFF -DLLAMA_USE_PREBUILT_UI=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
        -DCMAKE_C_FLAGS="$FLAGS" -DCMAKE_CXX_FLAGS="$FLAGS" -DCMAKE_BUILD_TYPE=Release
  echo "Building llama.cpp. This is the slow part (45-90 minutes)..."
  cmake --build build --target llama-server -j2      # 2 at a time, so it doesn't run out of memory
fi
"$HOME/llama.cpp/build/bin/llama-server" --version

mkdir -p "$HOME/models"
MODEL="$HOME/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"
wget -c -O "$MODEL" https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf

sudo tee /etc/systemd/system/llamaserver.service > /dev/null << SERVICE
[Unit]
Description=llama.cpp chat model for Pi Self-Learning AI
After=network.target

[Service]
User=$USER
ExecStart=$HOME/llama.cpp/build/bin/llama-server -m $MODEL --host 127.0.0.1 --port 8099 -t 3 -c 2048
Restart=always
RestartSec=10
Nice=5

[Install]
WantedBy=multi-user.target
SERVICE
sudo systemctl daemon-reload
sudo systemctl enable --now llamaserver
echo
echo "Done! The chat model is starting on port 8099 (give it a minute to load)."
echo "Check it:  curl http://127.0.0.1:8099/health"
