#!/usr/bin/env bash

cd /home/pi/energy_readery
source venv/bin/activate
python main.py > energy_reader.log