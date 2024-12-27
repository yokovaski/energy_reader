# Upgrade guideline

Go to the project directory and run the following commands:

```bash
git pull
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

Then update the config.json by checking for any changes in the example config file.

```bash
nano config.json
```

Finally, restart the service.

```bash
sudo systemctl restart energy-reader
```

If you have any issues, please check the [troubleshooting](troubleshooting.md) guide.