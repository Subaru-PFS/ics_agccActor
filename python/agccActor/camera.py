from expose import Exposure
from setmode import SetMode
from sequence import Sequence, SEQ_IDLE, SEQ_RUNNING, SEQ_ABORT
import writeFits

nCams = 6

class Camera(object):
    """ Subaru PFI AG cameras """

    def __init__(self, config):
        """ connect to AG cameras """

        simulator = int(config.get('agcc', 'simulator'))
        self.cams = [None, None, None, None, None, None]
        self.seq_stat = [SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE]
        self.seq_count = [0, 0, 0, 0, 0, 0]
        temp = float(config.get('agcc', 'temperature'))

        if simulator == 0:
            from fli import fli_camera

            self.numberOfCamera = fli_camera.numberOfCamera()
            for n in range(self.numberOfCamera):
                cam = fli_camera.Camera(n)
                cam.open()
                for k in range(nCams):
                    if cam.devsn == config.get('agcc', 'cam' + str(k + 1)):
                        self.cams[k] = cam
                        cam.agcid = k
                        cam.setTemperature(temp)
                        cam.regions = ((0, 0, 0), (0, 0, 0))
                        break
                else:
                    cam.close()
        else:
            from fli import fake_camera

            self.numberOfCamera = fake_camera.numberOfCamera()
            for n in range(self.numberOfCamera):
                devsn = config.get('agcc', 'cam' + str(n + 1))
                cam = fake_camera.Camera(n, devsn)
                cam.open()
                self.cams[n] = cam
                cam.agcid = n
                cam.setTemperature(temp)
                cam.regions = ((0, 0, 0), (0, 0, 0))

    def sendStatusKeys(self, cmd):
        """ Send our status keys to the given command. """ 

        cmd.inform('text="Number of AG cameras = %d"' % self.numberOfCamera)
        for n in range(nCams):
            if self.cams[n] != None:
                if self.cams[n].isReady():
                    tempstr = '%5.1f' % self.cams[n].getTemperature()
                    cmd.inform('agc%d_stat=0' % (n + 1))
                else:
                    tempstr = '<%5.1f>' % self.cams[n].temp
                    cmd.inform('agc%d_stat=1' % (n + 1))
                cmd.inform('text="[%d] %s SN=%s status=%s temp=%s regions=%s bin=(%d,%d) expArea=%s"'
                           % (n + 1, self.cams[n].devname, self.cams[n].devsn,
                           self.cams[n].getStatusStr(), tempstr, self.cams[n].regions,
                           self.cams[n].hbin, self.cams[n].vbin, self.cams[n].expArea))
            else:
                cmd.inform('agc%d_stat=2' % (n + 1))

    def expose(self, cmd, expTime, expType, cams, combined):
        """ Generate an 'exposure' image.

        Args:
           cmd      - a Command object to report to. Ignored if None.
           expTime  - the exposure time. 
           expType  - ("dark", "object", "test")
           cams     - list of active cameras [1-6]
           combined - Multiple FITS files/Single FITS file

        Returns:
           - NULL

        Keys:
           stat_cam[1-6]
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
            cmd.inform('text="Receive expose command"')

        active_cams = [self.cams[n] for n in cams_available]
        if expType == 'test':
            for n in cams_available:
                self.cams[n].expose_test()
                if not combined:
                    writeFits.wfits(cmd, self.cams[n])
            if combined:
                writeFits.wfits_combined(cmd, active_cams)
            for n in cams_available:
                if cmd:
                    tread = self.cams[n].getTotalTime()
                    cmd.inform('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
                    cmd.finish()
        else:
            expTime_ms = int(expTime * 1000)
            if expType == 'dark':
                dflag = True
            else:
                dflag = False

            exp_thr = Exposure(active_cams, expTime_ms, dflag, cmd, combined)
            exp_thr.start()

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
                if cmd:
                    cmd.inform('text="Send setframe command to AGC[%d]"' % (n + 1))
                if bx > 0:
                    self.cams[n].setHBin(bx)
                if by > 0:
                    self.cams[n].setVBin(by)
                self.cams[n].setFrame(cx, cy, sx, sy)
        if cmd:
            cmd.inform('text="Camera expose area set"')
            cmd.finish()

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
                if cmd:
                    cmd.inform('text="Send resetframe command to AGC[%d]"' % (n + 1))
                self.cams[n].resetFrame()
        if cmd:
            cmd.inform('text="Camera expose area reset"')
            cmd.finish()

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

        active_cams = [self.cams[n] for n in cams_available]
        setmode_thr = SetMode(active_cams, mode, cmd)
        setmode_thr.start()

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
                    cmd.respond('text="AGC[%d] readout mode: %d"' % (n + 1, mode))
        cmd.inform('text="Camera getmode command done"')
        cmd.finish()

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
                    cmd.respond('text="mode 0: %s"' % (s0))
                    cmd.respond('text="mode 1: %s"' % (s1))
                    cmd.inform('text="Camera getmodestring command done"')
                    cmd.finish()
                return
        if cmd:
            cmd.fail('text="camera busy or none attached, command ignored"')

    def settemperature(self, cmd, temp):
        """ Set CCD temperature

        Args:
           cmd     - a Command object to report to. Ignored if None.
           temp    - CCD temperature
        """

        busy = False
        for n in range(nCams):
            if self.cams[n] != None:
                if self.cams[n].isReady():
                    self.cams[n].setTemperature(temp)
                else:
                    busy = True
                    if cmd:
                        cmd.warn('text="Camera [%d] is busy"' % n)
        if cmd:
            if busy:
                cmd.fail('text="Camera settemperature command abort"')
            else:
                cmd.inform('text="Camera settemperature command done"')
                cmd.finish()

    def setregions(self, cmd, camid, regions_str):
        """ Set CCD regions of interested

        Args:
           cmd         - a Command object to report to. Ignored if None.
           camid       - Camera ID
           regions_str - Regions of interest to set
        """

        pars = regions_str.split(',')
        if len(pars) == 3:
            # only one region
            self.cams[camid].regions = ((pars[0], pars[1], pars[2]), (0, 0, 0))
        elif len(pars) == 6:
            # two regions
            self.cams[camid].regions = ((pars[0], pars[1], pars[2]), (pars[3], pars[4], pars[5]))
        else:
            # wrong number of parameters
            if cmd:
                cmd.fail('text="setregions command failed, invalid parameter: %s"' % regions_str)
            return

        if cmd:
            cmd.inform('text="setregions command done"')
            cmd.finish()

    def startsequence(self, cmd, seq_id, expTime, count, cams, combined):
        """ Start a exposure sequence

        Args:
           cmd      - a Command object to report to. Ignored if None.
           seq_id   - Sequence ID
           expTime  - exposure time
           count    - number of exposures
           cams     - list of active cameras [1-6]
        """

        cams_available = []
        for n in cams:
            if self.cams[n] != None and self.cams[n].isReady():
                cams_available.append(n)
            elif cmd:
                cmd.warn('text="Camera [%d] is not available"' % n)
        if len(cams_available) <= 0:
            if cmd:
                cmd.fail('text="No usable camera"')
            return

        if self.seq_stat[seq_id] != SEQ_IDLE:
            if cmd:
                cmd.fail('text="Sequence ID %d in used"' % (seq_id + 1))
            return
        self.seq_stat[seq_id] = SEQ_RUNNING
        self.seq_count[seq_id] = 0
        expTime_ms = int(expTime * 1000)
        if cmd:
            cmd.inform('inused_seq%d="YES"' % (seq_id + 1))

        active_cams = [self.cams[n] for n in cams_available]
        sequence_thr = Sequence(active_cams, expTime_ms, seq_id, count, self.seq_stat, self.seq_count, combined, cmd)
        sequence_thr.start()

    def stopsequence(self, cmd, seq_id):
        """ Stop a exposure sequence

        Args:
           cmd      - a Command object to report to. Ignored if None.
           seq_id   - Sequence ID
        """

        if self.seq_stat[seq_id] != SEQ_RUNNING:
            if cmd:
                cmd.fail('text="Sequence ID %d not in used"' % (seq_id + 1))
            return
        self.seq_stat[seq_id] = SEQ_ABORT

        if cmd:
            cmd.inform('text="Camera stopsequence [%d] command sent"' % (seq_id + 1))
            cmd.finish()

    def sequence_in_use(self, seq_id):
        """ Check if a sequence is in use """

        if self.seq_stat[seq_id] != SEQ_IDLE:
            return True
        else:
            return False

    def camera_stat(self, cam_id):
        """ Return the status of a camera """

        return self.cams[cam_id].getStatusStr()
