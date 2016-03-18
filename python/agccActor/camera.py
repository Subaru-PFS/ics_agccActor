import numpy
import time
import fli_camera
from twisted.internet import reactor
import thread

nCams = 6
POLL_TIME = 0.02

class Camera(object):
    """ Subaru PFI AG cameras """

    def __init__(self, config):
        """ connect to AG cameras """

        self.numberOfCamera = fli_camera.numberOfCamera()
        self.cams = [None, None, None, None, None, None]
        for n in range(self.numberOfCamera):
            cam = fli_camera.Camera(n)
            cam.open()
            for k in range(nCams):
                if cam.devsn == config.get('agcc', 'cam' + str(k + 1)):
                    self.cams[k] = cam
                    cam.agcid = k
                    break
            else:
                cam.close()

    def sendStatusKeys(self, cmd):
        """ Send our status keys to the given command. """ 

        cmd.inform('text="Number of AG cameras = %d"' % self.numberOfCamera)
        for n in range(nCams):
            if self.cams[n] != None:
                if self.cams[n].isReady():
                    tempstr = '%5.1f' % self.cams[n].getTemperature()
                else:
                    tempstr = '<%5.1f>' % self.cams[n].temp
                cmd.inform('text="[%d] %s S/N=%s status=%s temp=%s bin=(%d,%d) corner=(%d,%d) size=(%d,%d)"'
                           % (n + 1, self.cams[n].devname, self.cams[n].devsn, self.cams[n].getStatusStr(),
                           tempstr, self.cams[n].hbin, self.cams[n].vbin, self.cams[n].expArea[0],
                           self.cams[n].expArea[1], self.cams[n].expArea[2] - self.cams[n].expArea[0],
                           self.cams[n].expArea[3] - self.cams[n].expArea[1]))

    def expose(self, cmd, expTime, expType, cams):
        """ Generate an 'exposure' image.

        Args:
           cmd     - a Command object to report to. Ignored if None.
           expTime - the exposure time. 
           expType - ("dark", "object", "test")
           cams    - list of active cameras [1-8]

        Returns:
           - NULL

        Keys:
           exposureState
        """

        # check if any camera is available
        cams_available = []
        for n in cams:
            if self.cams[n] != None:
                cams_available.append(n)
        if len(cams_available) <= 0:
            if cmd:
                cmd.warn('text="No available cameras"')
                cmd.finish()
            return

        # check if all cameras are ready
        for n in cams_available:
            if not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return

        if not expType:
            expType = 'test'
        if cmd:
            for n in cams_available:
                cmd.inform('exposureState%d="exposing"' % (n + 1))

        if expType == 'test':
            for n in cams_available:
                self.cams[n].expose_test()
            if cmd:
                for n in cams_available:
                    tread = self.cams[n].tend - self.cams[n].tstart
                    cmd.inform('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
                    cmd.inform('exposureState%d="done"' % (n + 1))
                    cmd.finish()
        else:
            expTime_ms = int(expTime * 1000)
            if expType == 'dark':
                dflag = True
            else:
                dflag = False

            for n in cams_available:
                thread.start_new_thread(expose_call, (self.cams[n], expTime_ms, dflag))
            if cmd:
                reactor.callLater(POLL_TIME, self.expose_bottom, cmd, cams_available)

    def expose_bottom(self, cmd, cams):
        """ Wait for expose finishes and return the message """

        cams_busy = []
        for n in cams:
            if not self.cams[n].isReady():
                cams_busy.append(n)
            elif self.cams[n].tend > 0:
                tread = self.cams[n].tend - self.cams[n].tstart
                cmd.inform('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
                cmd.inform('exposureState%d="done"' % (n + 1))
            else:
                cmd.inform('text="AGC[%d]: Exposure aborted"')
                cmd.inform('exposureState%d="done"' % (n + 1))
        if len(cams_busy) > 0:
            reactor.callLater(POLL_TIME, self.expose_bottom, cmd, cams_busy)
        else:
            cmd.finish()

    def abort(self, cmd, cams):
        """ Abort current exposure

        Args:
           cmd     - a Command object to report to. Ignored if None.
           cams    - list of active cameras [1-8]
        """

        for n in cams:
            if self.cams[n] != None and not self.cams[n].isReady():
                cmd.inform('text="Send abort command to AGC[%d]"' % (n + 1))
                self.cams[n].cancelExposure()

    def setframe(self, cmd, cams, bx, by, cx, cy, sx, sy):
        """ set exposure area

        Args:
           cmd     - a Command object to report to. Ignored if None.
           cams    - list of active cameras [1-8]
           bx,by   - binning size
           cx,cy   - corner coordinate
           sx,sy   - exposure area size
        """

        for n in cams:
            if self.cams[n] != None and not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return

        for n in cams:
            if self.cams[n] != None:
                cmd.inform('text="Send resetframe command to AGC[%d]"' % (n + 1))
                if bx > 0:
                    self.cams[n].setHBin(bx)
                if by > 0:
                    self.cams[n].setHBin(by)
                self.cams[n].setFrame(cx, cy, sx, sy)
        if cmd:
            cmd.finish('text="Camera expose area set"')

    def resetframe(self, cmd, cams):
        """ reset exposure area

        Args:
           cmd     - a Command object to report to. Ignored if None.
           cams    - list of active cameras [1-8]
        """

        for n in cams:
            if self.cams[n] != None and not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return

        for n in cams:
            if self.cams[n] != None:
                cmd.inform('text="Send resetframe command to AGC[%d]"' % (n + 1))
                self.cams[n].resetFrame()
        if cmd:
            cmd.finish('text="Camera expose area reset"')

    def setmode(self, cmd, mode, cams):
        """ Set camera readout mode

        Args:
           cmd     - a Command object to report to. Ignored if None.
           mode    - readout mode
           cams    - list of active cameras [1-8]
        """

        cams_available = []
        for n in cams:
            if self.cams[n] != None:
                if not self.cams[n].isReady():
                    if cmd:
                        cmd.fail('text="camera busy, command ignored"')
                    return
                else:
                    cams_available.append(n)
        for n in cams_available:
            thread.start_new_thread(self.cams[n].setMode, (mode,))
            if cmd:
                cmd.inform('text="Send setmode(%d) command to AGC[%d]"' % (mode, n + 1))
        if cmd:
            reactor.callLater(POLL_TIME, self.setmode_bottom, cmd, cams_available)

    def setmode_bottom(self, cmd, cams):
        """ Wait for setmode finishes and return the message """

        cams_busy = []
        for n in cams:
            if not self.cams[n].isReady():
                cams_busy.append(n)
        if len(cams_busy) > 0:
            reactor.callLater(POLL_TIME, self.setmode_bottom, cmd, cams_busy)
        elif cmd:
            cmd.finish('text="Camera setmode command done"')

    def getmode(self, cmd, cams):
        """ Get camera readout mode

        Args:
           cmd     - a Command object to report to. Ignored if None.
           cams    - list of active cameras [1-8]
        """

        for n in cams:
            if self.cams[n] != None and not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                    return
        for n in cams:
            if self.cams[n] != None:
                mode = self.cams[n].getMode()
                if cmd:
                    cmd.inform('text="AGC[%d] readout mode: %d"' % (n + 1, mode))
        cmd.finish('text="Camera getmode command done"')

    def getmodestring(self, cmd):
        """ Get mode string from the first available camera

        Args:
           cmd     - a Command object to report to. Ignored if None.
        """

        for n in range(nCams):
            if self.cams[n] != None and self.cams[n].isReady():
                s0 = self.cams[n].getModeString(0)
                s1 = self.cams[n].getModeString(1)
                if cmd:
                    cmd.inform('text="mode 0: %s"' % (s0))
                    cmd.inform('text="mode 1: %s"' % (s1))
                    cmd.finish('text="Camera getmodestring command done"')
                return
        if cmd:
            cmd.fail('text="camera busy or none attached, command ignored"')


def expose_call(cam, expTime_ms, dflag):
    """ Concurrent exposure thread for camera readouts """
    cam.setExpTime(expTime_ms)
    cam.expose(dark=dflag)

