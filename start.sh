#!/usr/bin/env bash

cd /home/pi/energy_reader
source venv/bin/activate
python main.py >> error.log