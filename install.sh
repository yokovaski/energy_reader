#!/usr/bin/env bash

sudo apt-get update
sudo apt-get -y upgrade
sudo apt-get install -y git python3 python3-pip redis-server
cd "$(dirname "$0")"
sudo pip3 install virtualenv
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
sudo cp systemd/energy-reader.service /lib/systemd/system/energy-reader.service
sudo chmod 644 /lib/systemd/system/energy-reader.service
sudo systemctl daemon-reload
sudo systemctl enable energy-reader.service
sudo chmod +x start.sh

echo "--------------------------------------------"
echo "done!"
