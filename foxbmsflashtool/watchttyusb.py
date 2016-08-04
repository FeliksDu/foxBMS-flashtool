"""
foxBMS Software License

Copyright 2010-2016, Fraunhofer-Gesellschaft zur Foerderung 
                     der angewandten Forschung e.V.
All rights reserved.

BSD 3-Clause License

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

  1.  Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
  2.  Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
  3.  Neither the name of the copyright holder nor the names of its
      contributors may be used to endorse or promote products derived from
      this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

We kindly request you to use one or more of the following phrases to refer
to foxBMS in your hardware, software, documentation or advertising
materials:

"This product uses parts of foxBMS"
"This product includes parts of foxBMS"
"This product is derived from foxBMS"

If you use foxBMS in your products, we encourage you to contact us at:

CONTACT INFORMATION
Fraunhofer IISB ; Schottkystrasse 10 ; 91058 Erlangen, Germany
Dr.-Ing. Vincent LORENTZ
+49 9131-761-346
info@foxbms.org
www.foxbms.org

:since:     Mon Mar 21 21:08:30 CET 2016
:author:    Tim Fuehner <tim.fuehner@iisb.fraunhofer.de>
"""

import serial
import serial.tools.list_ports
import time 
import threading

# flags like on red development foxbms board. adapt accordingly
primaryCtrlerFlags = {"cts": False, "dsr": False}
secondaryCtrlerFlags = {"cts": False, "dsr": True}
CHECK_ISPRIMARY= False

class TTYUSBChecker(object):    
    def __init__(self, vid = 0x403, pid = 0x6015):
        self.vid = vid
        self.pid = pid
        self.connected = False
        self.port = None
        self.isPrimary = None

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
        if CHECK_ISPRIMARY:
            with serial.Serial(port=self.port.device) as _p:    
                if primaryCtrlerFlags["cts"] == _p.cts and primaryCtrlerFlags["dsr"] == _p.dsr:
                    self.isPrimary = True
                elif secondaryCtrlerFlags["cts"] == _p.cts and secondaryCtrlerFlags["dsr"] == _p.dsr:
                    self.isPrimary = False
                else:
                    self.isPrimary = None

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



