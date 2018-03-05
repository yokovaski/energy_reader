# Install energy_reader

## Update and install dependencies
* `sudo apt-get update && sudo apt-get -y upgrade && sudo apt-get install -y git python3 python3-pip`

## Clone this repo
* `cd ~ && git clone https://yokovaski@bitbucket.org/yokovaski/energy_reader.git`

## Install python dependencies
* `pip3 install setuptools`
* `pip3 install -r energy_reader/requirements.txt`

## Configuration
* Set the parameters in config.json

## Enable systemd service
* `sudo cp energy_reader/systemd/energy-reader.service /etc/systemd/system/`
* `sudo systemctl enable energy-reader.service`
* `sudo systemctl start energy-reader.service`

Check if the service is running with: `sudo systemctl status energy-reader`