#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys, os, time, atexit, re, datetime
from signal import SIGTERM
from device import Device

class Daemon:
  """
  A generic daemon class.
  Usage: subclass the Daemon class and override the run() method
  """
  
  def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
    self.stdin = stdin
    self.stdout = stdout
    self.stderr = stderr
    self.pidfile = pidfile
  
  def daemonize(self):
    """
    do the UNIX double-fork magic, see Stevens' "Advanced 
    Programming in the UNIX Environment" for details (ISBN 0201563177)
    http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
    """
    try: 
      pid = os.fork() 
      if pid > 0:
        # exit first parent
        sys.exit(0) 
    except OSError, e: 
      sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
      sys.exit(1)
  
    # decouple from parent environment
    #os.chdir("/") 
    os.setsid() 
    os.umask(0) 
  
    # do second fork
    try: 
      pid = os.fork() 
      if pid > 0:
        # exit from second parent
        sys.exit(0) 
    except OSError, e: 
      sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
      sys.exit(1) 
  
    # redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    si = file(self.stdin, 'r')
    so = file(self.stdout, 'a+')
    se = file(self.stderr, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())
  
    # write pidfile
    atexit.register(self.delpid)
    pid = str(os.getpid())
    file(self.pidfile,'w+').write("%s\n" % pid)
  
  def delpid(self):
    os.remove(self.pidfile)

  def start(self):
    """
    Start the daemon
    """
    # Check for a pidfile to see if the daemon already runs
    try:
      pf = file(self.pidfile,'r')
      pid = int(pf.read().strip())
      pf.close()
    except IOError:
      pid = None
  
    if pid:
      message = "pidfile %s already exist. Daemon already running?\n"
      sys.stderr.write(message % self.pidfile)
      sys.exit(1)
    
    # Start the daemon
    self.daemonize()
    self.run()

  def stop(self):
    """
    Stop the daemon
    """
    # Get the pid from the pidfile
    try:
      pf = file(self.pidfile,'r')
      pid = int(pf.read().strip())
      pf.close()
    except IOError:
      pid = None
  
    if not pid:
      message = "pidfile %s does not exist. Daemon not running?\n"
      sys.stderr.write(message % self.pidfile)
      return # not an error in a restart

    # Try killing the daemon process  
    try:
      while 1:
        os.kill(pid, SIGTERM)
        time.sleep(0.1)
    except OSError, err:
      err = str(err)
      if err.find("No such process") > 0:
        if os.path.exists(self.pidfile):
          os.remove(self.pidfile)
      else:
        print str(err)
        sys.exit(1)

  def restart(self):
    """
    Restart the daemon
    """
    self.stop()
    self.start()

  def run(self):
    """
    You should override this method when you subclass Daemon. It will be called after the process has been
    daemonized by start() or restart().
    """

class GadgetDevice:
  def __init__(self, address, name, hw_name):
    self.__address = address
    self.__name = name
    self.__hw_name = hw_name
    self.__low_battery = False

  @property
  def address(self):
    return self.__address

  @property
  def name(self):
    return self.__name

  @property
  def hw_name(self):
    return self.__hw_name

  @property
  def low_battery(self):
    return self.__low_battery

  def update(self, command):
    battery = re.match(".*LB:(\d).*", command)
    if battery:
      self.__low_battery = bool(int(battery.group(1)))


class GadgetsConnector(Daemon):
  ''' daemonized token connector '''
  def __init__(self, log_file=None):
    Daemon.__init__(self, '/tmp/turris-gadgets.pid')
    self.log = self.open_file(log_file)
    self.token = Device(device="/dev/ttyUSB0")
    self.reader = self.token.gen_lines(timeout=5)

  def open_file(self, filename):
    ''' file helper'''
    if filename:
      import os.path
      if os.path.exists(filename):
        file_mode = "a"
      else:
        file_mode = "w"
      return file(filename, file_mode)
    return None

  def send_raw(self, command):
    ''' send raw command to token '''
    self.token.send_command(command)
    return self.reader.next()

  def whoami(self):
    ''' token info''' 
    return self.send_raw('WHO AM I?')

  def getslot(self, index):
    ''' get gadget address registered on slot '''
    str_i = str(index).zfill(2)
    reply = self.send_raw('GET SLOT:%s' % str_i)
    slot = re.search("^SLOT:%s \[(\d{8}|-{8})\]" % str_i, reply)
    return slot.group(1)

  def cmd_read(self, line):
    m = re.search("^\[(\d{8})\]\s([a-zA-Z0-9_-]+)\s(.+)", line)
    if m.group():
      return [m.group(1), m.group(2), m.group(3)]
    return None

  def run(self):
    ''' only method called by daemon (start, restart) '''
    if self.log:
      self.log.write("%s\n" % self.whoami())
      for i in range(0, 32):
        self.log.write("SLOT: %s - %s\n" % (i, self.getslot(i)))
        self.log.flush()

class GadgetsAlarm(GadgetsConnector):
  ''' simple alarm class '''
  def __init__(self, temp_file=None, log_file=None):
    GadgetsConnector.__init__(self, log_file)
    self.temp_file = self.open_file(temp_file)
    self.devices = {
      '00000001': GadgetDevice('00000001', 'remote1L', 'RC-86K'), # arming device
      '00000002': GadgetDevice('00000002', 'remote1R', 'RC-86K'), # free use device
      '00000003': GadgetDevice('00000003', 'remote2L', 'RC-86K'),
      '00000004': GadgetDevice('00000004', 'remote2R', 'RC-86K'),
      '00000005': GadgetDevice('00000005', '', 'JA-81M'),
      '00000006': GadgetDevice('00000006', 'door1', 'JA-83M'),
      '00000007': GadgetDevice('00000007', 'door2', 'JA-83M'),
      '00000008': GadgetDevice('00000008', 'pir1', 'JA-83P'),
      '00000009': GadgetDevice('00000009', 'pir2', 'JA-83P'),
      '00000010': GadgetDevice('00000010', 'smokedetector', 'JA-85ST'),
      '00000011': GadgetDevice('00000011', '', 'JA-82SH'),
      '00000012': GadgetDevice('00000012', 'siren', 'JA-80L'),
      '00000013': GadgetDevice('00000013', 'thermostat', 'TP-82N'),
      '00000014': GadgetDevice('00000014', 'socket1', 'AC-88'), #PGX
      '00000015': GadgetDevice('00000015', 'socket2', 'AC-88')  #PGY
    }

    self.enroll = False
    self.armed = False
    self.alarm = False
    self.siren = 'NONE'
    self.PGX = False
    self.PGY = False
    self.temp = 0.0
    self.set_temp = 0.0

  def bool_parser(self, address, name, command):
    ''' parse data as bool from incomming message'''
    result =  re.search("^\[(\d{8})\].+%s:(.).*" % name, command)
    if result:
      device, state = result.groups()
      if device != address:
        self.log.write('ERROR: device address is different [%s] vs [%s]' % (device, address))
        return None
      if state:
        return bool(int(state))
    return None

  def action_parser(self, address, action, command):
    ''' check if action is preserved in message '''
    result =  re.search("^\[(\d{8})\].+(%s).*" % action, command)
    if result:
      device, state = result.groups()
      if device != address:
        self.log.write('ERROR: device address is different [%s] vs [%s]' % (device, address))
        return False
      if state:
        return True
    return False

  def send(self):
    ''' send command to dongle'''
    if self.siren in ['NONE', 'SLOW', 'FAST']:
      cmd = "TX ENROLL:%s PGX:%s PGY:%s ALARM:%s BEEP:%s" % (int(self.enroll),
        int(self.PGX), int(self.PGY), int(self.alarm), self.siren)
      self.log.write('CMD: %s\n' % cmd)
    else:
      return False
    if self.send_raw(cmd) == 'OK':
      self.log.write('CMD_OK\n')
      return True
    self.log.write('CMD_FAILED\n')
    return False

  def write2file(self):
    ''' write current temperature to CSV file '''
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
    self.temp_file.write("{0},{1}\n".format(date, self.temp))
    self.temp_file.flush()

  def temperature(self, command):
    ''' parse thermometer info and save it to class '''
    current = re.search("^\[(\d{8})\].+INT:(....)", command)
    if current:
      thermometer_id, temp = current.groups()
      self.temp = temp
      self.log.write('TEMP: %s' % temp)
      if self.temp_file:
        self.write2file()
    settemp = re.search("^\[(\d{8})\].+SET:(....)", command)
    if settemp:
      thermometer_id, temp = settemp.groups()
      self.set_temp = temp
      self.log.write('TEMPSET: %s' % temp)

  def run(self):
    ''' main loop - deamonized via Deamon class '''
    GadgetsConnector.run(self)
    while True:
      line = self.reader.next()
      
      if line != None:
        # skip answer lines
        if (line == 'OK') or (line == 'ERROR') or (line.startswith('TURRIS')):
          break
        
        data = self.cmd_read(line)
        # if device has registered, update gadget object
        if data[0] in self.devices:
          current_dev = self.devices[data[0]]
          self.log.write("DONGLE: %s DEVICE: %s DATA: %s\n" % (data[0], data[1], data[2]))
          current_dev.update(line)

          sensor = self.action_parser(current_dev.address, 'SENSOR', line)
          beacon = self.action_parser(current_dev.address, 'BEACON', line)
          tamper = self.action_parser(current_dev.address, 'TAMPER', line)

          if beacon:
            self.log.write('STATE: %s OK\n' % current_dev.name)
          
          if current_dev.name in ['remote1L', 'remote2L']:
            # ARM button event
            self.armed = self.bool_parser(current_dev.address, 'ARM', line)
            if self.armed:
              self.log.write('ARMED: %s\n' % current_dev.name)
            else:
              self.PGX = False
              self.alarm = False
              self.log.write('DISARMED: %s\n' % current_dev.name)

          elif current_dev.hw_name == 'JA-83M':
            # door sensor
            act = self.bool_parser(current_dev.address, 'ACT', line)
            if act and sensor:
              self.log.write('STATE: %s OPEN: %s\n' % (current_dev.name, act))
            if act and self.armed:
              self.PGX = True
              self.alarm = True
              self.log.write('ACTION: %s ALARM!\n' % current_dev.name)

          elif current_dev.hw_name == 'JA-83P':
            # PIR zone event
            act = self.bool_parser(current_dev.address, 'ACT', line)
            self.log.write('ZONE: %s STATE: %s\n' % (current_dev.name, (act or sensor)))
            if (act or sensor) and self.armed:
              self.alarm = True
              self.PGX = True
              self.log.write('ZONE: %s ALARM!\n' % current_dev.name)
          elif current_dev.hw_name == 'JA-82SH':
            if sensor:
              self.log.write('STATE: %s SENSOR\n' % current_dev.name)
          elif current_dev.hw_name == 'JA-85ST':
            if sensor:
              self.log.write('STATE: %s SENSOR\n' % (current_dev.name))
                self.log.write('ACTION: %s SMOKE!\n' % current_dev.name)
          elif current_dev.hw_name == 'JA-80L':
            blackout = self.bool_parser(current_dev.address, 'BLACKOUT', line)
            if blackout:
              self.log.write('ACTION: %s BLACKOUT!\n' % current_dev.name)
          elif current_dev.hw_name == 'TP-82N':
            self.temperature(line)
        else:
          self.log.write("Unregistered device: %s" % data[0])
        # finnaly send command
        self.send()     
      
      # report low battery event
      for dev in self.devices.keys():
        if self.devices[dev].low_battery:
          self.log.write("LOW_BATTERY: %s" % self.devices[dev].address)
      # write data to log immediatelly
      self.log.flush()
      
      time.sleep(0.1)
  
if __name__ == "__main__":
  daemon = GadgetsAlarm("thermometer.csv", "/var/log/gadgets.log")
  #daemon.run()
  
  if len(sys.argv) == 2:
    if 'start' == sys.argv[1]:
      daemon.start()
    elif 'stop' == sys.argv[1]:
      daemon.stop()
    elif 'restart' == sys.argv[1]:
      daemon.restart()
    else:
      print "Unknown command"
      sys.exit(2)
    sys.exit(0)
  else:
    print "usage: %s start|stop|restart" % sys.argv[0]
    sys.exit(2)
