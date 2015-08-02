# TURRIS:GADGETS simple daemon

Code in this repository is related to the [TURRIS:GADGETS](http://turris.cz/gadgets) project.
It is written in Python, which is available by default on router Turris.

##  Clone the repository 

  git clone git://github.com/trusnak/turris_gadgets_deamon.git
  
  NOTE: use git instead of http/https, because openwrt git package is compiled without curl

##  edit devices dict

  cd turris_gadgets_daemon
  vim daemon.py

  Example:
  '00000001<-- replace me': GadgetDevice('00000001<-- replace me!', 'remote1L', 'RC-86K'),   
  
## run the daemon

 ./daemon start
  
## Features
  - daemonized script
  - logging to /var/log/gadgets.log
  - very simple alarm Class
  - thermometer.csv is generated to current directory, can be turned off

## Missing features
  - sockets handler
  - more cleaner logs
  - REST API?
  - save data to database?

## Author
#### Created and maintained by
Tomas Rusnak
