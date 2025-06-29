#!/usr/bin/env python

import os
import base64
import numpy
import astropy.io.fits as pyfits

import opscore.protocols.keys as keys
import opscore.protocols.types as types

from opscore.utility.qstr import qstr

import centroidTools as ct
import dbRoutinesAGCC as dbRoutinesAGCC
nCams = 6

class AgccCmd(object):

    def __init__(self, actor):
        # This lets us access the rest of the actor.
        self.actor = actor
        

        # Declare the commands we implement. When the actor is started
        # these are registered with the parser, which will call the
        # associated methods when matched. The callbacks will be
        # passed a single argument, the parsed and typed command.
        #
        self.vocab = [
            ('ping', '', self.ping),
            ('status', '', self.status),
            ('expose', '@(test|dark|object) [<visit>] [<exptime>] '
                       '[<cameras>] [<combined>] [<centroid>] [<cMethod>] '
                       '[<threadDelay>] [@tecOFF]', self.expose),
            ('abort', '[<cameras>]', self.abort),
            ('reconnect', '', self.reconnect),
            ('shutter','@(close|open) [<cameras>]', self.shutterOps),
            ('setframe', '[<cameras>] [<bx>] [<by>] <cx> <cy> <sx> <sy>', self.setframe),
            ('resetframe', '[<cameras>]', self.resetframe),
            ('getmode', '[<cameras>]', self.getmode),
            ('setmode', '<mode> [<cameras>]', self.setmode),
            ('getmodestring', '', self.getmodestring),
            ('settemperature', '[<cameras>] <temperature>', self.settemperature),
            ('setregions', '<camera> <regions>', self.setregions),
            ('startsequence', '<sequence> <exptime> <count> <cameras> [<combined>]', self.startsequence),
            ('stopsequence', '<sequence>', self.stopsequence),
            ('inusesequence', '<sequence>', self.inusesequence),
            ('inusecamera', '<camera>', self.inusecamera),
            ('insertVisit', '<visit>', self.insertVisit),
            ('setCentroidParams','[<nmin>] [<thresh>] [<deblend>]',
             self.setCentroidParams),
            ('setImageParams', '', self.setImageParams),
        ]

        # Define typed command arguments for the above commands.
        self.keys = keys.KeysDictionary("agcc_agcc", (1, 1),
                                        keys.Key("exptime", types.Float(), help="The exposure time"),
                                        keys.Key("cameras", types.String(), help="List of active cameras[1-6]"),
                                        keys.Key("bx", types.Int(), help="Serial Binning"),
                                        keys.Key("by", types.Int(), help="Parallel Binning"),
                                        keys.Key("cx", types.Int(), help="Corner x coordinate"),
                                        keys.Key("cy", types.Int(), help="Corner y coordinate"),
                                        keys.Key("sx", types.Int(), help="Serial size"),
                                        keys.Key("sy", types.Int(), help="Parallel size"),
                                        keys.Key("mode", types.Int(), help="Readout mode"),
                                        keys.Key("temperature", types.Float(), help="CCD temperature"),
                                        keys.Key("camera", types.Int(), help="Camera ID"),
                                        keys.Key("regions", types.String(), help="Regions of interest, x1,y1,d1,x2,y2,d2"),
                                        keys.Key("sequence", types.Int(), help="Sequence ID"),
                                        keys.Key("count", types.Int(), help="Number of exposures in sequence"),
                                        keys.Key("visit", types.Int(), help="pfs_visit_id assigned by IIC"),
                                        keys.Key("combined", types.Int(), help="0/1: multiple FITS files/single FITS file"),
                                        keys.Key("centroid", types.Int(), help="0/1: if 1 do centroid else don't"),
                                        keys.Key("threadDelay", types.Float(), help="Time of delay when executing exposure threading"),
                                        keys.Key("fwhmx", types.Float(), help="X fwhm for centroid routine"),
                                        keys.Key("nmin", types.Int(), help="minimum number of points for sep"),
                                        keys.Key("thresh", types.Float(), help="threshhold for finding spots"),
                                        keys.Key("deblend", types.Float(), help="deblend_cont for sep"),
                                        keys.Key("cMethod", types.String(), help="method to use for centroiding (win, sep)"),
                                        )
        # initialize centroid parameters
        self.setCentroidParams(None)


    def ping(self, cmd):
        """Query the actor for liveness/happiness."""

        cmd.respond("text='I am AG camera actor'")
        cmd.finish()

    def reconnect(self, cmd):
        """Reconnect camera devices"""

        #self.actor.connectCamera(cmd, self.actor.actorConfig)
        self.actor.reloadCamera(cmd, self.actor.actorConfig)
        cmd.inform('text="AG cameras connected!"')
        cmd.finish()

    def status(self, cmd):
        """Report status and version; obtain and send current data"""

        self.actor.sendVersionKey(cmd)
        self.actor.camera.sendStatusKeys(cmd)

        cmd.inform('text="Present!"')
        cmd.finish()

    def setOrGetVisit(self, cmd):
        """Set and return the visit passed in the command keys, or fetch one from gen2. """

        self.cmd = cmd
        cmdKeys = cmd.cmd.keywords

        # When we start a new visit, always reset frame counter.
        self.frameSeq = 0
        if 'visit' in cmdKeys:
            self.visit = cmdKeys['visit'].values[0]
        else:
            ret = self.actor.cmdr.call(actor='gen2', cmdStr='getVisit caller=agcc',
                                       forUserCmd=cmd, timeLim=15.0)
            if ret.didFail:
                raise RuntimeError("getNextFilename failed getting a visit number in 15s!")
            self.visit = self.actor.models['gen2'].keyVarDict['visit'].valueList[0]

        return self.visit

    def insertVisit(self, cmd):

        cmdKeys = cmd.cmd.keywords
        visit = cmdKeys['visit'].values[0]
        dbRoutinesAGCC.writeVisitToDB(visit)
        cmd.finish()

    def shutterOps(self, cmd):

        cmdKeys = cmd.cmd.keywords
        shutterMode = cmdKeys[0].name
        cams = []
        if 'cameras' in cmdKeys:
            camList = cmdKeys['cameras'].values[0]
            for cam in camList:
                k = int(cam) - 1
                if k < 0 or k >= nCams:
                    cmd.error('text="camera list error: %s"' % camList)
                    cmd.fail()
                    return
                cams.append(k)
        else:
            for k in range(nCams):
                cams.append(k)

        
        if shutterMode == 'open':
            self.actor.camera.openShutter(cmd, cams)
        if shutterMode == 'close':
            self.actor.camera.closeShutter(cmd, cams)

        cmd.finish()


    def expose(self, cmd):
        """Take an exposure. combined=0/1."""

        cmdKeys = cmd.cmd.keywords
        expType = cmdKeys[0].name
        visit = self.setOrGetVisit(cmd)
        self.actor.logger.info(f'Starting exposure of type {expType} for pfs_visit_id={visit}')

        # Ask gen2 updating the telescope status
        self.actor.cmdr.call(actor='gen2',
                             cmdStr=f'updateTelStatus caller=agcc visit={visit}',
                             timeLim=5.0)

        if 'exptime' in cmdKeys:
            expTime = cmdKeys['exptime'].values[0]
        else:
            expTime = 0.0

        combined = True
        if 'combined' in cmdKeys:
            if cmdKeys['combined'].values[0] == 0:
                combined = False

        centroid = False
        if 'centroid' in cmdKeys:
            if cmdKeys['centroid'].values[0] == 1:
                centroid = True

        # moved this to configurable option
        #self.setCentroidParams(cmd)

        cMethod = "sep"
        if 'cMethod' in cmdKeys:
            cMethod = cmdKeys['cMethod'].values[0]

        if 'threadDelay' in cmdKeys:
            threadDelay = cmdKeys['threadDelay'].values[0]
        else:
            threadDelay = 0.0

        if 'tecOFF' in cmdKeys:
            tecOFF = True
        else:
            tecOFF = False

        cmd.inform(f'text="TEC OFF status = {tecOFF}"')      
        cmd.inform(f'text="Setting threading delay of {threadDelay} ms"')            

        self.actor.logger.info(f'Setting image params: {visit=} {expTime=} {combined=} {centroid=} {cMethod=} {threadDelay=} {tecOFF=}')
        self.setImageParams(cmd)

        magFit = self.iParms['magFit']
        cmd.inform(f'text="read magFit = {magFit}"')

        cams = []
        if 'cameras' in cmdKeys:
            camList = cmdKeys['cameras'].values[0]
            for cam in camList:
                k = int(cam) - 1
                if k < 0 or k >= nCams:
                    cmd.error('text="camera list error: %s"' % camList)
                    cmd.fail()
                    return
                cams.append(k)
        else:
            cams = self.actor.camera.runningCameras() 
            cmd.inform(f'text="found cameras: {cams}"')

        # Report TEC before taking exposure
        self.actor.camera.reportTEC(cmd)
        cmd.inform(f'text="pfs_visit_id: {visit}"')
        self.actor.camera.expose(cmd, expTime, expType, cams, combined, centroid, visit, 
                                 self.cParms, cMethod, self.iParms, threadDelay=threadDelay,
                                 tecOFF=tecOFF)


    def abort(self, cmd):
        """Abort an exposure"""

        cmdKeys = cmd.cmd.keywords
        cams = []
        if 'cameras' in cmdKeys:
            camList = cmdKeys['cameras'].values[0]
            for cam in camList:
                k = int(cam) - 1
                if k < 0 or k >= nCams:
                    cmd.error('text="camera list error: %s"' % camList)
                    cmd.fail()
                    return
                cams.append(k)
        else:
            for k in range(nCams):
                cams.append(k)

        self.actor.camera.abort(cmd, cams)
        cmd.finish('text="Last exposure aborted!"')

    def setframe(self, cmd):
        """Set exposure area, binning=(bx,by) corner=(cx,cy) size=(sx,sy)"""

        cmdKeys = cmd.cmd.keywords
        cams = []
        if 'cameras' in cmdKeys:
            camList = cmdKeys['cameras'].values[0]
            for cam in camList:
                k = int(cam) - 1
                if k < 0 or k >= nCams:
                    cmd.error('text="camera list error: %s"' % camList)
                    cmd.fail()
                    return
                cams.append(k)
        else:
            for k in range(nCams):
                cams.append(k)

        if 'bx' in cmdKeys:
            bx = cmdKeys['bx'].values[0]
        else:
            bx = 0
        if 'by' in cmdKeys:
            by = cmdKeys['by'].values[0]
        else:
            by = 0
        if not 'cx' in cmdKeys or not 'cy' in cmdKeys or not 'sx' in cmdKeys or not 'sy' in cmdKeys:
            cmd.error('text="reqired parameters (cx,cy,sx,sy) missing"')
            cmd.fail()
            return
        cx = cmdKeys['cx'].values[0]
        cy = cmdKeys['cy'].values[0]
        sx = cmdKeys['sx'].values[0]
        sy = cmdKeys['sy'].values[0]

        self.actor.camera.setframe(cmd, cams, bx, by, cx, cy, sx, sy)

    def resetframe(self, cmd):
        """Reset exposure area"""

        cmdKeys = cmd.cmd.keywords
        cams = []
        if 'cameras' in cmdKeys:
            camList = cmdKeys['cameras'].values[0]
            for cam in camList:
                k = int(cam) - 1
                if k < 0 or k >= nCams:
                    cmd.error('text="camera list error: %s"' % camList)
                    cmd.fail()
                    return
                cams.append(k)
        else:
            for k in range(nCams):
                cams.append(k)

        self.actor.camera.resetframe(cmd, cams)

    def setmode(self, cmd):
        """Set current readout mode (0=4MHz, 1=500KHz)"""

        cmdKeys = cmd.cmd.keywords
        mode = cmdKeys['mode'].values[0]

        cams = []
        if 'cameras' in cmdKeys:
            camList = cmdKeys['cameras'].values[0]
            for cam in camList:
                k = int(cam) - 1
                if k < 0 or k >= nCams:
                    cmd.error('text="camera list error: %s"' % camList)
                    cmd.fail()
                    return
                cams.append(k)
        else:
            for k in range(nCams):
                cams.append(k)

        self.actor.camera.setmode(cmd, mode, cams)

    def getmode(self, cmd):
        """Get current readout mode (0=4MHz, 1=500KHz)"""

        cmdKeys = cmd.cmd.keywords
        cams = []
        if 'cameras' in cmdKeys:
            camList = cmdKeys['cameras'].values[0]
            for cam in camList:
                k = int(cam) - 1
                if k < 0 or k >= nCams:
                    cmd.error('text="camera list error: %s"' % camList)
                    cmd.fail()
                    return
                cams.append(k)
        else:
            for k in range(nCams):
                cams.append(k)

        self.actor.camera.getmode(cmd, cams)

    def getmodestring(self, cmd):
        """Get current readout mode string."""

        cmdKeys = cmd.cmd.keywords
        self.actor.camera.getmodestring(cmd)

    def settemperature(self, cmd):
        """Set CCD temperature"""

        cmdKeys = cmd.cmd.keywords
        temperature = cmdKeys['temperature'].values[0]
        if 'cameras' in cmdKeys:
            
            camList = cmdKeys['cameras'].values[0]
            cmd.inform(f'text="Setting temerature for AG cameras = {camList}"')

            for cam in camList:
                n = int(cam) - 1
                cmd.inform(f'text="Setting camera AG{n+1} to {temperature}"')
                self.actor.camera.setcamtemperature(cmd, n, temperature)
        else:
            self.actor.camera.settemperature(cmd, temperature)
        cmd.finish('text="Setting camera TEC finished!"')

    def setregions(self, cmd):
        """Set regoins of interest"""

        cmdKeys = cmd.cmd.keywords
        camid = cmdKeys['camera'].values[0]
        regions = cmdKeys['regions'].values[0]
        self.actor.camera.setregions(cmd, camid, regions)

    def startsequence(self, cmd):
        """Start a exposure sequence"""

        cmdKeys = cmd.cmd.keywords
        seq_id = cmdKeys['sequence'].values[0] - 1
        expTime = cmdKeys['exptime'].values[0]
        count = cmdKeys['count'].values[0]
        combined = True
        if 'combined' in cmdKeys:
            if cmdKeys['combined'].values[0] == 0:
                combined = False

        cams = []
        camList = cmdKeys['cameras'].values[0]
        for cam in camList:
            k = int(cam) - 1
            if k < 0 or k >= nCams:
                cmd.error('text="camera list error: %s"' % camList)
                cmd.fail()
                return
            cams.append(k)
        if count < 0:
            cmd.error('text="parameter count invalid: %d"' % count)
            cmd.fail()
        elif len(cams) <= 0:
            cmd.error('text="No usable camera"')
            cmd.fail()
        elif expTime <= 0:
            cmd.error('text="exposure time invalid: %f"' % expTime)
            cmd.fail()
        else:
            self.actor.camera.startsequence(cmd, seq_id, expTime, count, cams, combined)

    def stopsequence(self, cmd):
        """Stop a exposure sequence"""

        cmdKeys = cmd.cmd.keywords
        seq_id = cmdKeys['sequence'].values[0] - 1
        self.actor.camera.stopsequence(cmd, seq_id)

    def inusesequence(self, cmd):
        """Check if a sequence is running"""

        cmdKeys = cmd.cmd.keywords
        seq_id = cmdKeys['sequence'].values[0] - 1
        if seq_id < 0 or seq_id >= nCams:
            cmd.fail('text="sequence id error: %d"' % (seq_id + 1))
            return
        if self.actor.camera.sequence_in_use(seq_id):
            cmd.respond('inused_seq%d="YES"' % (seq_id + 1))
        else:
            cmd.respond('inused_seq%d="NO"' % (seq_id + 1))
        cmd.finish()

    def inusecamera(self, cmd):
        """Check if a camera is in use"""

        cmdKeys = cmd.cmd.keywords
        cam_id = cmdKeys['camera'].values[0] - 1
        if cam_id < 0 or cam_id >= nCams:
            cmd.fail('text="camera id error: %d"' % (cam_id + 1))
            return
        stat = self.actor.camera.camera_stat(cam_id)
        cmd.respond('stat_cam%d="%s"' % (cam_id + 1, stat))
        cmd.finish()

    def setCentroidParams(self, cmd):

        """
        top level routine for setting centroid parameters. Reads the defaults from teh config fil,e
        then changes any specified in the keywords argument. 

        """

        self.cParms = ct.getCentroidParams(cmd)
        thresh = self.cParms['thresh'] 
        deblend = self.cParms['deblend'] 
        nmin = self.cParms['nmin']
        if cmd is not None:
            cmd.finish(f'text="centroid parameters set thresh/deblend/nmin = {thresh} {deblend} {nmin}"')

    def setImageParams(self, cmd):

        """
        top level routine for setting image parameters. Reads the defaults from the config file,
        then changes any specified in the keyword arguments.
        """
        self.actor.logger.info(f'Setting image parameters: {cmd=}')
        self.iParms = ct.getImageParams(cmd)
