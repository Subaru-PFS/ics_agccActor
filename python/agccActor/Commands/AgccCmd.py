#!/usr/bin/env python

import os
import base64
import numpy
import astropy.io.fits as pyfits

import opscore.protocols.keys as keys
import opscore.protocols.types as types

from opscore.utility.qstr import qstr

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
            ('expose', '@(test|dark|object) [<exptime>] [<cameras>] [<combined>]', self.expose),
            ('abort', '[<cameras>]', self.abort),
            ('reconnect', '', self.reconnect),
            ('setframe', '[<cameras>] [<bx>] [<by>] <cx> <cy> <sx> <sy>', self.setframe),
            ('resetframe', '[<cameras>]', self.resetframe),
            ('getmode', '[<cameras>]', self.getmode),
            ('setmode', '<mode> [<cameras>]', self.setmode),
            ('getmodestring', '', self.getmodestring),
            ('settemperature', '<temperature>', self.settemperature),
            ('setregions', '<camera> <regions>', self.setregions),
            ('startsequence', '<sequence> <exptime> <count> <cameras> [<combined>]', self.startsequence),
            ('stopsequence', '<sequence>', self.stopsequence),
            ('inusesequence', '<sequence>', self.inusesequence),
            ('inusecamera', '<camera>', self.inusecamera),
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
                                        keys.Key("combined", types.Int(), help="0/1: multiple FITS files/single FITS file"),
                                        )


    def ping(self, cmd):
        """Query the actor for liveness/happiness."""

        cmd.respond("text='I am AG camera actor'")
        cmd.finish()

    def reconnect(self, cmd):
        """Reconnect camera devices"""

        self.actor.connectCamera(cmd, self.actor.config)
        cmd.inform('text="AG cameras connected!"')
        cmd.finish()

    def status(self, cmd):
        """Report status and version; obtain and send current data"""

        self.actor.sendVersionKey(cmd)
        self.actor.camera.sendStatusKeys(cmd)

        cmd.inform('text="Present!"')
        cmd.finish()

    def expose(self, cmd):
        """Take an exposure. combined=0/1."""

        cmdKeys = cmd.cmd.keywords
        expType = cmdKeys[0].name
        if 'exptime' in cmdKeys:
            expTime = cmdKeys['exptime'].values[0]
        else:
            expTime = 0.0
        combined = True
        if 'combined' in cmdKeys:
            if cmdKeys['combined'].values[0] == 0:
                combined = False

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

        self.actor.camera.expose(cmd, expTime, expType, cams, combined)

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
        self.actor.camera.settemperature(cmd, temperature)

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

