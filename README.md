# Install energy_reader

## Clone this repo
* `cd ~ && git clone https://yokovaski@bitbucket.org/yokovaski/energy_reader.git`

## Install energy_reader
* `sudo ./install.sh`

## Configuration
* Set the parameters in config.json

## start systemd service
* `sudo systemctl start energy-reader.service`

Check if the service is running with: `sudo systemctl status energy-reader`
## Tests
The tests use `unittest` and `unittest.mock`; hardware, Redis, MQTT and HTTP are mocked, but the packages from `requirements.txt` must be installed (use the venv).
* `python3 -m unittest discover -p 'test_*.py'`
* Coverage: `pip install coverage`, then `coverage run -m unittest discover -p 'test_*.py' && coverage report`
