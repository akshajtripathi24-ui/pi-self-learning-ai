# 1. Install it

Run every command on the Pi, one line at a time.

```bash
sudo apt update
sudo apt install -y git python3-numpy
git clone https://github.com/akshajtripathi24-ui/pi-self-learning-ai ~/selflearning
cd ~/selflearning
bash setup-autostart.sh
```

| Command | What it does |
|---|---|
| `sudo apt install -y git python3-numpy` | Installs git and **numpy**, the Python package for fast math with big lists of numbers (the AI's brain is about 100,000 numbers) |
| `git clone … ~/selflearning` | Downloads this project into a folder called `selflearning` |
| `bash setup-autostart.sh` | Starts it in the background and makes it start whenever the Pi boots |

Then open **http://raspberrypi.local:8100** (or `http://YOUR-PI-IP:8100`).

## Running next to your other projects
It uses port **8100**: the stock tracker uses 8000, the Space Station Tracker 8080 and the Docking AI 8090, so all four can run together. It runs at slightly lower priority so the others stay quick. **The chatbot (part 2) uses all 4 processor cores**, so pause the Docking AI while the chatbot practices.

## Useful commands
```bash
systemctl is-active selflearning          # is it running? (should say: active)
journalctl -u selflearning -n 30          # the last 30 lines of its log
sudo systemctl restart selflearning       # restart it (the math AI keeps what it learned)
```

## Update to the newest version
```bash
cd ~/selflearning && git pull && sudo systemctl restart selflearning
```

## Uninstall
```bash
sudo systemctl disable --now selflearning
sudo rm /etc/systemd/system/selflearning.service
rm -rf ~/selflearning
```

**Next:** [2. The self-taught math AI](02-math-ai.md)
