# Get list of hardware to find Dummy device
http://192.168.3.173:8080/json.htm?type=hardware

# Adding a required dummy hardware device
http://192.168.3.173:8080/json.htm?type=command&param=addhardware&htype=15&port=1&name=ez2&enabled=true

# Adding a virtual sensor (p1 Electricity)
http://192.168.3.173:8080/json.htm?type=createdevice&idx=2&sensorname=TESTp1Electricity&sensormappedtype=0xFA01

# Adding a virtual sensor (p1 Gas)
http://192.168.3.173:8080/json.htm?type=createdevice&idx=2&sensorname=p1Gas&sensormappedtype=0xFB02