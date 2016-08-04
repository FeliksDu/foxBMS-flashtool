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

    def __init__(self, parent = None, vid = 0x403, pid = 0x6015, sleepTime = 1):
        watchttyusb.TTYUSBCheckerThread.__init__(self, vid, pid, sleepTime)
        self.parent = parent

    def onConnect(self):
        watchttyusb.TTYUSBCheckerThread.onConnect(self)
        wx.CallAfter(self.parent.registerDevice, self.port, self.isPrimary)

    def onDisconnect(self):
        wx.CallAfter(self.parent.unregisterDevice)


class DummyUSBWatch(USBWatch):

    def isConnected(self):
        return os.path.exists('ttyusb.dummy')

class FlashThread(threading.Thread):

    def __init__(self, parent):
        self.parent = parent
        threading.Thread.__init__(self)
        self.canceling = False

    def run(self):
        wx.CallAfter(self.parent.enableWidgets, False)
        wx.CallAfter(self.parent.dontTouch, True)
        # FIXME args
        with foxflasher.FoxFlasher(port = self.parent.port.device, address =
                0x08000000, dummy = self.parent.dummy) as l:
            l.erase()
            # write main
            with open(self.parent.path_fw, 'rb') as f:
                data = map(lambda c: ord(c), f.read())
            l.write(data)
            l.verify(data)
            # write header
            l.address = 0x080FFF00
            with open(self.parent.path_fw_h, 'rb') as f:
                data = map(lambda c: ord(c), f.read())
            l.write(data)
            l.verify(data)
        wx.CallAfter(self.parent.enableWidgets, True)
        wx.CallAfter(self.parent.dontTouch, False)
        wx.CallAfter(logging.info, '__all_done__')


class FBInariPanel(wx.Panel):

    def __init__(self, parent, path_fw = None, path_fw_h = None, showFP =
            True, dummy = False, swallow = False):
        self.parent = parent
        self.path_fw = path_fw
        self.path_fw_h = path_fw_h
        self.deviceFound = False
        self.dummy = dummy
        self.firmwareSelected = False
        self.showFP = showFP
        self._resources = xrc.EmptyXmlResource()
        self._resources.Load(_getpath('xrc', 'inarift.xrc'))
        pre = wx.PrePanel()
        self._resources.LoadOnPanel(pre, parent, "inari_p")
        self.PostCreate(pre)

        xrc.XRCCTRL(self, 'flash_b').Bind(wx.EVT_BUTTON, self.onFlash)

        xrc.XRCCTRL(self, 'firmware_fp').Bind(wx.EVT_FILEPICKER_CHANGED,
                self.onFirmwareSelected)
        xrc.XRCCTRL(self, 'firmware_header_fp').Bind(wx.EVT_FILEPICKER_CHANGED,
                self.onFirmwareSelected)

        if not self.path_fw is None:
            xrc.XRCCTRL(self, 'firmware_fp').SetPath(self.path_fw)
        if not self.path_fw_h is None:
            xrc.XRCCTRL(self, 'firmware_header_fp').SetPath(self.path_fw_h)

        if not self.path_fw is None and not self.path_fw_h is None and os.path.isfile(self.path_fw) and os.path.isfile(self.path_fw_h):
            self.firmwareSelected = True
        else:
            self.firmwareSelected = False

        self.setFlashButton()
        self.startUSBChecker()

    def onFirmwareSelected(self, evt):
        self.path_fw = xrc.XRCCTRL(self, 'firmware_fp').GetPath()
        self.path_fw_h = xrc.XRCCTRL(self, 'firmware_header_fp').GetPath()
 
        if os.path.isfile(self.path_fw) and os.path.isfile(self.path_fw_h):
            self.firmwareSelected = True
        else:
            self.firmwareSelected = False
        self.setFlashButton()

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
            xrc.XRCCTRL(self, 'flash_b').Enable(self.firmwareSelected)
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
        th = FlashThread(self)
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

    def setPaths(self, root):
        _build = os.path.join(root, 'build', 'src', 'general')
        self.path_fw = os.path.join(_build, 'foxbms_flash.bin')
        self.path_fw_h = os.path.join(_build, 'foxbms_flashheader.bin')
        xrc.XRCCTRL(self, 'firmware_fp').SetPath(self.path_fw)
        xrc.XRCCTRL(self, 'firmware_header_fp').SetPath(self.path_fw_h)
        if os.path.isfile(self.path_fw) and os.path.isfile(self.path_fw_h):
            self.firmwareSelected = True
        else:
            self.firmwareSelected = False




class CustomConsoleHandler(logging.StreamHandler):
 
    def __init__(self, parent):
        logging.StreamHandler.__init__(self)
        self.parent = parent
 
    def emit(self, record):
        msg = self.format(record)
        wx.CallAfter(self.parent.writeLog, msg + "\n")


class FBInariFrame(wx.Frame):
    PROGRESS_RE = re.compile('\[\s*(\d+)/(\d+)\] (.*)')

    def __init__(self, parent, path_fw_h = None, path_fw = None, dummy =
            False):
        dummy_st = ''
        if dummy:
            dummy_st = ' (dry-run mode)'
        wx.Frame.__init__(self, parent, -1, title = 'foxBMS Inari FlashTool%s' % dummy_st)
        self.parent = parent
        ms = wx.BoxSizer(wx.VERTICAL)
        self.fbipanel = FBInariPanel(self, path_fw_h = path_fw_h, path_fw =
                path_fw, dummy = dummy)
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

    def __init__(self, path_fw = None, path_fw_h = None, dummy = False):
        self.path_fw_h = path_fw_h
        self.path_fw = path_fw
        self.dummy = dummy
        wx.App.__init__(self, False)

    def OnInit(self):
        frame = FBInariFrame(None, path_fw = self.path_fw, path_fw_h =
                self.path_fw_h, dummy = self.dummy)
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
    import argparse
    parser = argparse.ArgumentParser(description='foxBMS---Inari flash tool')

    parser.add_argument('-v', '--verbosity', action='count', default=1, help="increase output verbosity")
    parser.add_argument('--header', type=lambda x: getpath(parser, x, 'r'),
            metavar='HEADER',
            help='Header part of firmware')
    parser.add_argument('--main', type=lambda x: getpath(parser, x, 'r'),
            metavar='MAIN',
            help='Main part of firmware')
    parser.add_argument('--dry', '-d', action='store_true', help='')

    args = parser.parse_args()

    if args.verbosity == 1:
        logging.basicConfig(level = logging.INFO)        
    elif args.verbosity > 1:
        logging.basicConfig(level = logging.DEBUG)
    else:
        logging.basicConfig(level = logging.ERROR)

    app = FBInariApp(path_fw = args.main, path_fw_h = args.header, dummy =
            args.dry)

    app.MainLoop()


if __name__ == '__main__':
    main()



