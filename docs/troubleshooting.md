# Troubleshooting

This document provides a list of common issues and solutions for the Energy Reader project.

## Introduction

This document provides a list of common issues and solutions for the Energy Reader project.

## Logs

The first step in troubleshooting is to check the logs. The logs are located in the same directory. The common filename
is `energy_reader.log`.

If that does not help, you can increase the log level by enable debug mode. To do this set "debug" to true in the
`config.json` file.

If that also does not help, you can try to run the script in the terminal. This will give you more information about
the error. To do this, open a terminal and navigate to the project directory. Then run the following command:

```bash
sudo rm energy_reader.log
source venv/bin/activate
python main.py
```