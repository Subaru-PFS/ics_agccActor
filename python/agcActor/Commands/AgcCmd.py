#!/usr/bin/env python

import os
import base64
import numpy
import astropy.io.fits as pyfits

import opscore.protocols.keys as keys
import opscore.protocols.types as types

from opscore.utility.qstr import qstr

nCams = 6

class AgcCmd(object):

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
            ('expose', '@(test|dark|object) [<time>] [<cameras>]', self.expose),
            ('abort', '[<cameras>]', self.abort),
            ('reconnect', '', self.reconnect),
            ('setframe', '[<cameras>] [<bx>] [<by>] <cx> <cy> <sx> <sy>', self.setframe),
            ('resetframe', '[<cameras>]', self.resetframe),
            ('getmode', '[<cameras>]', self.getmode),
            ('setmode', '<mode> [<cameras>]', self.setmode),
            ('getmodestring', '', self.getmodestring),
        ]

        # Define typed command arguments for the above commands.
        self.keys = keys.KeysDictionary("agc_agc", (1, 1),
                                        keys.Key("time", types.Float(), help="The exposure time"),
                                        keys.Key("cameras", types.String(), help="List of active cameras[1-8]"),
                                        keys.Key("bx", types.Int(), help="Serial Binning"),
                                        keys.Key("by", types.Int(), help="Parallel Binning"),
                                        keys.Key("cx", types.Int(), help="Corner x coordinate"),
                                        keys.Key("cy", types.Int(), help="Corner y coordinate"),
                                        keys.Key("sx", types.Int(), help="Serial size"),
                                        keys.Key("sy", types.Int(), help="Parallel size"),
                                        keys.Key("mode", types.Int(), help="Readout mode"),
                                        )


    def ping(self, cmd):
        """Query the actor for liveness/happiness."""

        cmd.finish("text='I am AG camera actor'")

    def reconnect(self, cmd):
        """Reconnect camera devices"""

        self.actor.connectCamera(cmd, self.actor.config)
        cmd.finish('text="AG cameras connected!"')

    def status(self, cmd):
        """Report status and version; obtain and send current data"""

        self.actor.sendVersionKey(cmd)
        self.actor.camera.sendStatusKeys(cmd)

        cmd.inform('text="Present!"')
        cmd.finish()

    def expose(self, cmd):
        """Take an exposure. Does not centroid."""

        cmdKeys = cmd.cmd.keywords
        expType = cmdKeys[0].name
        if 'time' in cmdKeys:
            expTime = cmdKeys['time'].values[0]
        else:
            expTime = 0.0

        cams = []
        if 'cameras' in cmdKeys:
            camList = cmdKeys['cameras'].values[0]
            for cam in camList:
                k = int(cam) - 1
                if k < 0 or k >= nCams:
                    cmd.error('text="camera list error: %s"' % camList)
                    cmd.finish()
                    return
                cams.append(k)
        else:
            for k in range(nCams):
                cams.append(k)

        self.actor.camera.expose(cmd, expTime, expType, cams)

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
                    cmd.finish()
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
                    cmd.fail('text="camera list error: %s"' % camList)
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
            cmd.fail('text="reqired parameters (cx,cy,sx,sy) missing"')
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
                    cmd.finish()
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

