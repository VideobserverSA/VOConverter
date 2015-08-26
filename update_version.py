__author__ = "Rui"

import configparser
from datetime import date

config = configparser.ConfigParser()
config.read("version.ini")

current_version = config["Vo Converter"]["version"]
# increment the current version minor
a = current_version.split('.')
a[2] = str(int(a[2]) + 1)
new_version = ".".join(a)
config["Vo Converter"]["version"] = new_version
today = date.today()
config["Vo Converter"]["date"] = today.strftime("%d/%m/%Y")
f = open("version.ini", "w")
config.write(f)

