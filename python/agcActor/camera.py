import numpy
import time
import fli_camera
from twisted.internet import reactor

nCams = 6
POLL_TIME = 0.1

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
                if cam.devsn == config.get('agc', 'cam' + str(k + 1)):
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
                    tempstr = '%4.1f' % self.cams[n].getTemperature()
                else:
                    tempstr = '%4.1f' % self.cams[n].temp
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

        expTime_ms = int(expTime * 1000)
        if expType == 'dark':
            dflag = 1
        else:
            dflag = 0

        if expType == 'test':
            for n in cams_available:
                self.cams[n].expose_test()
            if cmd:
                for n in cams_available:
                    cmd.inform('exposureState%d="done"' % (n + 1))
                    cmd.finish()
        else:
            for n in cams_available:
                self.cams[n].setExpTime(expTime_ms)
                self.cams[n].expose(dark=dflag)
            if cmd:
                reactor.callLater(POLL_TIME, self.expose_bottom, cmd, cams_available)

    def expose_bottom(self, cmd, cams):
        """ Wait for expose finishes and return the message """

        cams_busy = []
        for n in cams:
            if self.cams[n] != None and not self.cams[n].isReady():
                cams_busy.append(n)
            else:
                cmd.inform('exposureState%d="done"' % (n + 1))
        if len(cams_busy) > 0:
            reactor.callLater(POLL_TIME, self.expose_bottom, cmd, cams_busy)
        elif cmd:
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
