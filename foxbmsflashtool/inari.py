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

:since:     Thu Mar 31 12:24:57 CEST 2016
:author:    Tim Fuehner <tim.fuehner@iisb.fraunhofer.de>

Usage:
    inari --help

"""

import wx
from wx import xrc
from wx import aui
import wx.aui
import os
import sys
import shutil
import watchttyusb
import foxflasher
import threading
import logging
import re

def _getpath(*args):
    path = [os.path.dirname(__file__)] + list(args)
    return os.path.join(*path)


class USBWatch(watchttyusb.TTYUSBCheckerThread):
    '''
    Thread watching the USB port for connections.
    '''

    def __init__(self, parent = None, vid = 0x403, pid = 0x6015, sleepTime = 1):
        '''
        :param parent:  parent wx.Window
        :param vid:     vendor id of USB device
        :param pid:     PID of USB device
        :param sleepTime:   interval between polls
        '''
        watchttyusb.TTYUSBCheckerThread.__init__(self, vid, pid, sleepTime)
        self.parent = parent

    def onConnect(self):
        '''
        Handler, triggered whenever the queried device is detected.
        '''
        watchttyusb.TTYUSBCheckerThread.onConnect(self)
        wx.CallAfter(self.parent.registerDevice, self.port, self.isPrimary)

    def onDisconnect(self):
        '''
        Handler, triggered whenever the queried device is detached.
        '''
        wx.CallAfter(self.parent.unregisterDevice)


class DummyUSBWatch(USBWatch):

    def isConnected(self):
        return os.path.exists('ttyusb.dummy')


class FlashData(object):

    KEYS = [
            'bootloader_body', 
            'bootloader_header', 
            'application_body',
            'application_header', 
            ]

    DEFAULT_ADDRESSES = [ 
            0x08000000,
            0x08007F00,
            0x08008000,
            0x080FFF00,
            ]

    def __init__(self):
        self._data = {}
        self._addresses = dict(zip(self.KEYS, self.DEFAULT_ADDRESSES))

    def findFiles(self, root = '.', target = 'primary'):
        '''
        :returns:   body, header
        '''

        _root = os.path.abspath(root)
        _build = os.path.join(_root, 'build', target, 'foxBMS-%s' % target, 'src', 'general')
        return os.path.join(_build, 'foxbms_flash.bin'), os.path.join(_build, 'foxbms_flashheader.bin')

    def __setitem__(self, key, fname):
        self._data[key] = fname
    
    def __getitem__(self, key):
        return self._data[key]

    def _getIdx(self, key):
        return self.KEYS.index(key)

    def __contains__(self, key):
        return (key in self._data and not self._data[key] is None)

    def setAddress(self, key, address):
        self._addresses[key] = address

    def getAddress(self, key):
        return self._addresses[key]

    def hasBootloader(self):
        return ('bootloader_body' in self._data and \
                not self._data['bootloader_body'] is None and \
                'bootloader_header' in self._data and \
                not self._data['bootloader_header'] is None)

    def hasApplication(self):
        return ('application_body' in self._data and \
                not self._data['application_body'] is None and \
                'application_header' in self._data and \
                not self._data['application_header'] is None)

    def iterData(self):
        for k in self.KEYS:
            if k in self._data and not self._data[k] is None:
                yield self._data[k], self._addresses[k]

    def isDataComplete(self):
        # at least application data must be present
        return self.hasApplication()

class FlashThread(threading.Thread):

    def __init__(self, parent, flashdata):
        self.parent = parent
        threading.Thread.__init__(self)
        self.canceling = False
        self._data = []
        self.flashdata = flashdata

    def resetData(self):
        self._data = []

    def addData(self, target, address, fname):
        self._data += [(target, address, fname)]


    def run(self):

        wx.CallAfter(self.parent.enableWidgets, False)
        wx.CallAfter(self.parent.dontTouch, True)

        with foxflasher.FoxFlasher(port = self.parent.port.device, address =
                0x08000000, dummy = self.parent.dummy) as l:

            # if bootloader to be flashed, full erase
            # else erase only application section
            if self.flashdata.hasBootloader():
                l.erase
            else:
                l.extendedErase("AllButBootloader")

            for fn, addr in self.flashdata():
                with open(fn, 'rb') as f:
                    data = map(lambda c: ord(c), f.read())
                l.address = addr
                l.write(data)
                l.verify(data)

        wx.CallAfter(self.parent.enableWidgets, True)
        wx.CallAfter(self.parent.dontTouch, False)
        wx.CallAfter(logging.info, '__all_done__')


class FBInariPanel(wx.Panel):

    def __init__(self, parent, flashdata = None, showFP =
            True, dummy = False, swallow = False):
        self.parent = parent
        self.deviceFound = False
        self.dummy = dummy
        self.flashdata = flashdata
        self.showFP = showFP
        self._resources = xrc.EmptyXmlResource()
        self._resources.Load(_getpath('xrc', 'inarift.xrc'))
        pre = wx.PrePanel()
        self._resources.LoadOnPanel(pre, parent, "inari_p")
        self.PostCreate(pre)

        xrc.XRCCTRL(self, 'flash_b').Bind(wx.EVT_BUTTON, self.onFlash)
        xrc.XRCCTRL(self, 'find_b').Bind(wx.EVT_BUTTON, self.onFind)

        for k in self.flashdata.KEYS:
            xrc.XRCCTRL(self, '%s_fp' % k).Bind(wx.EVT_FILEPICKER_CHANGED, self.onFirmwareSelected)

        self.setControls()
        self.setFlashButton()
        self.startUSBChecker()

    def setControls(self):
        for k in self.flashdata.KEYS:
            if k in self.flashdata:
                xrc.XRCCTRL(self, '%s_fp' % k).SetPath(self.flashdata[k])

    def onFirmwareSelected(self, evt):
        for k in self.flashdata.KEYS:
            _path = xrc.XRCCTRL(self, '%s_fp' % k).GetPath()
            if os.path.isfile(_path):
                self.flashdata[k] = _path
            else:
                self.flashdata[k] = None
        self.setFlashButton()

    def onFind(self, evt):
        _path = xrc.XRCCTRL(self, 'root_d').GetPath()
        if _path is None:
            return
        self.setPaths(
                _path,
                xrc.XRCCTRL(self, 'board_c').GetStringSelection()
                )

    def registerDevice(self, port, prim = None):
        self.deviceFound = True
        self.port = port
        self.isPrimary = prim
        if self.dummy:
            xrc.XRCCTRL(self, 'device_st').SetLabel('Device found. (file: ttyusb.dummy found)')
        else:
            xrc.XRCCTRL(self, 'device_st').SetLabel('Device found. Port: %s %s' % (self.port.device, {True:"Primary", False:"Secondary"}.get(self.isPrimary, '')))
        self.setFlashButton()

    def unregisterDevice(self):
        self.deviceFound = False
        self.port = None
        if self.dummy:
            xrc.XRCCTRL(self, 'device_st').SetLabel('No device found.  (file: ttyusb.dummy not found)')
        else:
            xrc.XRCCTRL(self, 'device_st').SetLabel('No device found.')
        self.setFlashButton()

    def setFlashButton(self):
        if self.deviceFound:
            xrc.XRCCTRL(self, 'flash_b').SetBitmap(wx.Bitmap(_getpath('xrc', 'upload.png')))
            xrc.XRCCTRL(self, 'flash_b').SetBitmapDisabled(wx.Bitmap(_getpath('xrc', 'upload.png')))
            xrc.XRCCTRL(self, 'flash_b').Enable(self.flashdata.isDataComplete())
        else:
            xrc.XRCCTRL(self, 'flash_b').SetBitmap(wx.Bitmap(_getpath('xrc', 'noupload.png')))
            xrc.XRCCTRL(self, 'flash_b').SetBitmapDisabled(wx.Bitmap(_getpath('xrc', 'noupload.png')))
            xrc.XRCCTRL(self, 'flash_b').Enable(False)

    def startUSBChecker(self):
        if self.dummy:
            self.usbChecker = DummyUSBWatch(self)
        else:
            self.usbChecker = USBWatch(self)
        self.usbChecker.start()

    def stopUSBChecker(self):
        self.usbChecker.stop = True
        self.usbChecker.join()

    def onFlash(self, evt):
        th = FlashThread(self, self.flashdata)
        th.start()

    def dontTouch(self, enabled):
        if enabled:
            self.dT = DontTouchDialog(self)
            self.dT.ShowModal()
        else:
            self.dT.EndModal(wx.ID_OK)

    def enableWidgets(self, enable = True):
        for widget in self.GetChildren(): 
            widget.Enable(enable) 

    def setPaths(self, root, target = 'primary'):
        b,h = self.flashdata.findFiles(root, target)
        xrc.XRCCTRL(self, 'application_body_fp').SetPath(b)
        xrc.XRCCTRL(self, 'application_header_fp').SetPath(h)
        self.onFirmwareSelected(None)


class CustomConsoleHandler(logging.StreamHandler):
 
    def __init__(self, parent):
        logging.StreamHandler.__init__(self)
        self.parent = parent
 
    def emit(self, record):
        msg = self.format(record)
        wx.CallAfter(self.parent.writeLog, msg + "\n")


class FBInariFrame(wx.Frame):
    PROGRESS_RE = re.compile('\[\s*(\d+)/(\d+)\] (.*)')

    def __init__(self, parent, flashdata=None, dummy=False):
        dummy_st = ''
        if dummy:
            dummy_st = ' (dry-run mode)'
        wx.Frame.__init__(self, parent, -1, title = 'foxBMS Inari FlashTool%s' % dummy_st)
        self.parent = parent
        ms = wx.BoxSizer(wx.VERTICAL)
        self.fbipanel = FBInariPanel(self, flashdata=flashdata, dummy = dummy)
        ms.Add(self.fbipanel, 0, wx.EXPAND | wx.ALL, 5)
        self.dt = self.fbipanel._resources.LoadPanel(self, "details_p")
        ms.Add(self.dt, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(ms)
        self.Fit()

        xrc.XRCCTRL(self, 'clear_b').Bind(wx.EVT_BUTTON, self.onClear)
        #xrc.XRCCTRL(self, 'details_tc').SetMinSize((-1, 150))
        #xrc.XRCCTRL(self, 'commands_box').SetMinSize((200, 200))
        xrc.XRCCTRL(self, 'progress').SetSize((-1, 3))
        xrc.XRCCTRL(self, 'progress').SetMaxSize((-1, 3))
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.installLogger()

    def installLogger(self):
        _rootlogger = logging.getLogger()
        self.logHandler = CustomConsoleHandler(self)
        _rootlogger.addHandler(self.logHandler)

    def OnClose(self, evt):
        # FIXME veto on not ready
        self.fbipanel.stopUSBChecker()
        evt.Skip()

    def onClear(self, evt):
        xrc.XRCCTRL(self, 'details_tc').Clear()

    def writeLog(self, msg):
        if msg == '__all_done__':
            self.setProgress(1, 1)
            return

        g = self.PROGRESS_RE.match(msg)
        if g: 
            if 'written' in g.group(3):
                self.setProgress(0.5*(int(g.group(1)) - 1), int(g.group(2)))
            elif 'read' in g.group(3):   
                self.setProgress(0.5 * int(g.group(2)) + 0.5*(int(g.group(1)) - 1), int(g.group(2)))

        _ds = xrc.XRCCTRL(self, 'details_tc').GetDefaultStyle()
        _c = _ds.GetTextColour()

        if 'error:' in msg:
            _ds.SetTextColour(wx.Colour(240, 0, 0))
            xrc.XRCCTRL(self, 'details_tc').SetDefaultStyle(_ds)
        elif 'warning:' in msg:
            _ds.SetTextColour(wx.Colour(120, 120, 0))
            xrc.XRCCTRL(self, 'details_tc').SetDefaultStyle(_ds)
        elif 'finished successfully' in msg:
            _ds.SetTextColour(wx.Colour(0, 160, 0))
            xrc.XRCCTRL(self, 'details_tc').SetDefaultStyle(_ds)
        else:
            _ds.SetTextColour(wx.Colour(0, 0, 0))
            xrc.XRCCTRL(self, 'details_tc').SetDefaultStyle(_ds)

        xrc.XRCCTRL(self, 'details_tc').AppendText(msg)
        _ds.SetTextColour(_c)

    def setProgress(self, prog, ran):
        xrc.XRCCTRL(self, 'progress').SetRange(ran) 
        xrc.XRCCTRL(self, 'progress').SetValue(prog)

class FBInariApp(wx.App):

    def __init__(self, flashdata=None, dummy = False):
        self.flashdata = flashdata
        self.dummy = dummy
        wx.App.__init__(self, False)

    def OnInit(self):
        frame = FBInariFrame(None, flashdata=self.flashdata, dummy = self.dummy)
        self.SetTopWindow(frame)
        frame.Show()
        return True

    def OnExit(self):
        pass
        #wx.App.OnExit(self)

class DontTouchDialog(wx.Dialog):

    def __init__(self, parent):
        pre = wx.PreDialog()
        self.parent = parent
        parent._resources.LoadOnDialog(pre, parent, "dont_touch_d")
        self.PostCreate(pre)
        self.Fit()

def getpath(parser, arg, mode = 'r'):
    if mode == 'r' and not os.path.isfile(arg):
        parser.error("The file %s does not exist!" % arg)
    elif mode == 'r|d' and not os.path.exists(arg):
        parser.error("The file/directory %s does not exist!" % arg)
    elif mode == 'w' and not os.path.isdir(os.path.dirname(os.path.abspath(arg))):
        parser.error("%s is not a valid directory!" % os.path.dirname(os.path.abspath(arg)))
    else:
        return os.path.abspath(arg)

def main():

    flashdata = FlashData()

    import argparse
    parser = argparse.ArgumentParser(description='foxBMS---Inari flash tool')

    parser.add_argument('-v', '--verbosity', action='count', default=1, help="increase output verbosity")

    for k in flashdata.KEYS:
        parser.add_argument('--' + k, type=lambda x: getpath(parser, x, 'r'), metavar=k.upper)

    parser.add_argument('--dry', '-d', action='store_true', help='')

    args = parser.parse_args()

    if args.verbosity == 1:
        logging.basicConfig(level = logging.INFO)        
    elif args.verbosity > 1:
        logging.basicConfig(level = logging.DEBUG)
    else:
        logging.basicConfig(level = logging.ERROR)
    

    app = FBInariApp(flashdata = flashdata, dummy = args.dry)

    app.MainLoop()


if __name__ == '__main__':
    main()



