#!/usr/bin/env bash

sudo systemctl stop energy-reader.service
cd "$(dirname "$0")"
git pull
source venv/bin/activate
pip install -r requirements.txt
deactivate
sudo systemctl start energy-reader.service