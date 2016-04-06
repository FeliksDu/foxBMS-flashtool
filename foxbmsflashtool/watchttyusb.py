"""
:since:     Mon Mar 21 21:08:30 CET 2016
:author:    Tim Fuehner <tim.fuehner@iisb.fraunhofer.de>
$Id$
"""

import serial
import serial.tools.list_ports
import time 
import threading


class TTYUSBChecker(object):

    def __init__(self, vid = 0x403, pid = 0x6015):
        self.vid = vid
        self.pid = pid
        self.connected = False
        self.port = None

    def isConnected(self):
        for port in list(serial.tools.list_ports.comports()):
            if port.vid == self.vid and port.pid == self.pid:
                self.port = port
                return True
        self.port = None
        return False

    def __str__(self):
        return 'port: %s, pid %s, %s' % (hex(self.port), hex(self.pid), 
                'connected' if self.isConnected() else 'not connected')


class TTYUSBCheckerThread(TTYUSBChecker, threading.Thread):

    def __init__(self, port = 0x403, pid = 0x6015, sleepTime = 1):
        self.sleepTime = sleepTime
        TTYUSBChecker.__init__(self, port, pid)
        threading.Thread.__init__(self)
        self.connected = False
        self.stop = False

    def onConnect(self):
        print 'connected'

    def onDisconnect(self):
        print 'disconnected'

    def run(self):
        while not self.stop:
            _c = self.isConnected()
            if self.connected != _c:
                if _c: self.onConnect()
                else: self.onDisconnect()
            self.connected = _c
            time.sleep(self.sleepTime)



if __name__ == "__main__":
    print str(TTYUSBChecker())



