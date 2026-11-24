# 5. Troubleshooting

**First, three checks:**
```bash
systemctl is-active selflearning          # should say: active
journalctl -u selflearning -n 30          # the last 30 lines of the log
sudo systemctl restart selflearning       # restart it (the math AI keeps what it learned)
```

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'numpy'` | Run `sudo apt install -y python3-numpy`, then restart. |
| `Address already in use` | Something else is on port 8100, or a second copy is running. Run `sudo systemctl stop selflearning; pkill -f selflearning/server.py; sudo systemctl start selflearning`. |
| The page doesn't load | Use `http://YOUR-PI-IP:8100` (find the IP with `hostname -I`). Don't forget `:8100`. |
| The math AI's score dropped after a level-up | Normal! Each new level is harder, so its score falls, then climbs again. That's the dips in the chart. |
| It got worse at an old level | It can forget things it isn't practicing. A fifth of its questions review earlier levels to stop that. |
| Speed says **🌡️ Cooling down** | The Pi got hotter than 78 °C, so the math AI is resting until it's under 70 °C. A fan or heatsink helps. Check with `vcgencmd measure_temp`. |
| Chatbot: **No language model found** | Ollama (64-bit) or the llama.cpp server (32-bit) isn't running. See [3. The chatbot](03-chatbot.md). Check with `curl http://127.0.0.1:11434/api/tags` (Ollama) or `curl http://127.0.0.1:8099/health` (llama.cpp). |
| Chatbot: **the model … isn't downloaded** | Run `ollama pull qwen2.5:0.5b`. |
| Chatbot: lots of **bad questions thrown away** | Normal for a small model: it often forgets the format. They're skipped, and only good questions count. |
| The whole Pi is slow | Pause the Docking AI and the math AI while the chatbot practices, or stop the collapse experiment. |
| The collapse experiment says **Stopped** after a restart | Restarting stops a running experiment. Start it again. |

Something else? Check the [build log](06-build-log.md).
