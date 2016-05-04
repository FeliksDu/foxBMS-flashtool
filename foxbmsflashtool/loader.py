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

:since:     Tue Mar 22 13:49:40 CET 2016
:author:    Tim Fuehner <tim.fuehner@iisb.fraunhofer.de>
"""

import stm32loader
import logging
import argparse
import sys
import os
import time

class CommandDummy(object):

    def __init__(self):
        pass

    def open(self, aport='/dev/tty.usbserial-ftCYPMYJ', abaudrate=115200):
        logging.debug("*** Open %s %d" % (aport, abaudrate))

    def readMemory(self, addr, lng):
        logging.debug("*** Read memory command")

    def writeMemory(self, addr, data):
        logging.debug("*** Write memory command")
        lng = len(data)
        alllng = lng
        offs = 0
        while lng > 256:
            logging.info("[%d/%d] written" % (alllng - lng, alllng))
            offs = offs + 256
            addr = addr + 256
            lng = lng - 256
            time.sleep(0.007)
        logging.info("Write %(len)d bytes at 0x%(addr)X" % {'addr': addr, 'len': 256})

    def cmdEraseMemory(self, sectors = None):
        logging.debug("*** Erase memory command")

    def initChip(self):
        logging.debug("*** Init chip command")

    def cmdGet(self):
        return 1

    def cmdGetID(self):
        return 0x413

    def releaseChip(self):
        logging.debug("*** Go command")

    def cmdGo(self, addr):
        logging.debug("*** Go command")

class STM32Loader(object):

    PORT = '/dev/tty.usbserial-ftCYPMYJ'
    BAUD = 115200

    def __init__(self, port = None, bauds = None,
            address = 0x08000000, goaddress = -1, bytes = 256, **kwargs):

        self.port = port
        self.baud = bauds
        if self.port is None:
            self.port = self.PORT
        if self.baud is None:
            self.baud = self.BAUD
        self.address = address
        self.go_addr = goaddress
        self.bytes = bytes
        if kwargs.get('dummy', False):
            self.cmd = CommandDummy()
        else:
            self.cmd = stm32loader.CommandInterface()
        self.cmd.open(self.port, self.baud)
        try:
            self.cmd.initChip()
        except:
            IOError("Can't init. Ensure that BOOT0 is enabled and reset device")
        self.bootversion = self.cmd.cmdGet()
        logging.info("Bootloader version %X" % self.bootversion)
        self.id = self.cmd.cmdGetID()
        logging.info("Chip id: 0x%x (%s)" % (self.id, stm32loader.chip_ids.get(self.id, "Unknown")))
        self.veriFail = None

    def __enter__(self):
        return self

    def __exit__(self ,type, value, traceback):
        self.close()

    @staticmethod
    def open(port = None, baud = None):
        return STM32Loader(port, baud)

    def close(self):
        self.cmd.releaseChip()

    def erase(self):
        self.cmd.cmdEraseMemory()

    def write(self, data):
        self.cmd.writeMemory(self.address, data)

    def read(self, buflen = None):
        if buflen is None:
            buflen = self.buflen
        return self.cmd.readMemory(self.address, buflen)

    def verify(self, data):
        verify = self.cmd.readMemory(self.address, len(data))
        if data == verify:
            return True
        else:
            self.veriFail = str(len(data)) + ' vs ' + str(len(verify)) + '\n'
            for i in xrange(0, len(data)):
                if data[i] != verify[i]:
                    self.veriFail += hex(i) + ': ' + hex(data[i]) + ' vs ' + hex(verify[i]) + '\n'
            logging.debug(self.veriFail)
            return False

    def goAddress(self):
        self.cmd.cmdGo(self.go_addr)


def main():
    parser = argparse.ArgumentParser(description='foxBMS---STM32 flash tool', 
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog = '''\
Example:
%s --port COM3 --erase --write --verify build/src/general/foxbms_flash.bin 

Copyright (c) 2015, 2016 Fraunhofer IISB.
All rights reserved.
This program has been released under the conditions of the 3-clause BSD
license.

Uses stm32loader

Author: Ivan A-R <ivan@tuxotronic.org>
Project page: http://tuxotronic.org/wiki/projects/stm32loader

This file is part of stm32loader.

stm32loader is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation; either version 3, or (at your option) any later
version.

stm32loader is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
for more details.

You should have received a copy of the GNU General Public License
along with stm32loader; see the file COPYING3.  If not see
<http://www.gnu.org/licenses/>.''' % sys.argv[0])

    parser.add_argument('-v', '--verbosity', action='count', default=0, help="increase output verbosity")
    parser.add_argument('--erase', '-e', action='store_true', help='erase firmware')
    parser.add_argument('--read',  '-r', action='store_true', help='read and store firmware')
    parser.add_argument('--write',  '-w', action='store_true', help='writes firmware')
    parser.add_argument('--verify', '-y', action='store_true', help='verify the firmware')
    parser.add_argument('--bytes', '-s', type=int, help='bytes to read from the firmware')
    parser.add_argument('--bauds', '-b', type=int, default=115200, help='transfer speed (bauds)')
    parser.add_argument('--port', '-p', type=str, default='/dev/tty.usbserial-ftCYPMYJ', help='ttyUSB port')
    parser.add_argument('--address', '-a', type=int, default=0x08000000, help='target address')
    parser.add_argument('--goaddress', '-g', type=int, default=-1, help='start address (use -1 for default)')
    parser.add_argument('firmware', metavar = 'FIRMWARE FILE', help='firmware binary')

    args = parser.parse_args()

    if args.verbosity == 1:
        logging.basicConfig(level = logging.INFO)
    elif args.verbosity > 1:
        logging.basicConfig(level = logging.DEBUG)
    else:
        logging.basicConfig(level = logging.ERROR)

    if args.read:
        if args.erase:
            parser.error('Cannot use --erase together with --read')
        if args.write:
            parser.error('Cannot use --write together with --read')


    with STM32Loader(**vars(args)) as loader:
        if args.write or args.verify:
            with open(args.firmware, 'rb') as f:
                data = map(lambda c: ord(c), f.read())

        if args.erase:
            loader.erase()

        if args.write:
            loader.write(data)

        if args.verify:
            loader.verify(data)

        if args.read:
            rdata = loader.read()
            with open(args.firmware, 'wb') as f:
                f.write(''.join(map(chr,rdata)))

        if args.goaddress > -1:
            loader.goAddress()


if __name__ == "__main__":
    main()
    
