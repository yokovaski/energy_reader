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