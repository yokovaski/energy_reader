#!/usr/bin/env bash

cd /home/pi/energy_reader || exit
source venv/bin/activate
python main.py &>> sysout.log