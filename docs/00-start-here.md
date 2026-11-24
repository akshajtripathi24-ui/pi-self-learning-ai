# 0. Start here: the whole project, step by step

**Time:** about 15 minutes for parts 1 and 3. Part 2 (the chatbot) takes another 15–60 minutes to set up, depending on your Pi.
**You need:** a Raspberry Pi 4 already set up with Raspberry Pi OS and connected to the internet, and a computer or phone on the same Wi-Fi.

---

**Step 1. Install it.**
```bash
sudo apt update
sudo apt install -y git python3-numpy
git clone https://github.com/akshajtripathi24-ui/pi-self-learning-ai ~/selflearning
cd ~/selflearning
bash setup-autostart.sh
```
✅ You're done when it says `Done!` and `systemctl is-active selflearning` says `active`.

**Step 2. Open it.** On any device on your Wi-Fi, open **http://raspberrypi.local:8100** (or `http://YOUR-PI-IP:8100`).
✅ You're done when the **🧮 Math AI** tab shows questions flying by, mostly ❌ at first.

**Step 3. Watch the math AI teach itself.** Check back every 10 minutes. Watch the level go up, and the ❌ turn into ✅. Ask it a question in **🙋 Ask it a question**.
✅ You're done when it reaches level 3 (about 15–30 minutes).

**Step 4. Run the collapse experiment.** Open **🔬 Collapse experiment** and press **▶ Start the experiment**. Come back in about half an hour. Then tick **keep the real facts**, run it again, and compare the charts.
✅ You're done when you've seen the sentences get weirder round after round.

**Step 5 (optional). Set up the chatbot.** Follow [3. The self-quizzing chatbot](03-chatbot.md).
✅ You're done when the **💬 Chatbot** tab shows its own word problems.

---

**Stuck?** See [5. Troubleshooting](05-troubleshooting.md). The [build log](06-build-log.md) has every problem we hit.
