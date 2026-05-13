#!/usr/bin/env python

import opscore.protocols.keys as keys
import opscore.protocols.types as types

from agccActor import centroid, database

nCams = 6


class AgccCmd(object):
    """Command vocabulary for the AGCC tron actor.

    Registers the command grammar and keyword dictionary used by the
    actor parser, and provides one handler per command.
    """

    def __init__(self, actor):
        """Register the command vocabulary and keyword dictionary.

        Parameters
        ----------
        actor : object
            The owning :class:`AgccActor` instance.
        """
        # This lets us access the rest of the actor.
        self.actor = actor

        # Declare the commands we implement. When the actor is started
        # these are registered with the parser, which will call the
        # associated methods when matched. The callbacks will be
        # passed a single argument, the parsed and typed command.
        #
        self.vocab = [
            ("ping", "", self.ping),
            ("status", "", self.status),
            (
                "expose",
                "@(test|dark|object) [<visit>] [<exptime>] "
                "[<cameras>] [<combined>] [<centroid>] [<cMethod>] "
                "[<threadDelay>] [@tecOFF]",
                self.expose,
            ),
            ("abort", "[<cameras>]", self.abort),
            ("reconnect", "", self.reconnect),
            ("shutter", "@(close|open) [<cameras>]", self.shutterOps),
            ("setframe", "[<cameras>] [<bx>] [<by>] <cx> <cy> <sx> <sy>", self.setframe),
            ("resetframe", "[<cameras>]", self.resetframe),
            ("getmode", "[<cameras>]", self.getmode),
            ("setmode", "<mode> [<cameras>]", self.setmode),
            ("getmodestring", "", self.getmodestring),
            ("settemperature", "[<cameras>] <temperature>", self.settemperature),
            ("setregions", "<camera> <regions>", self.setregions),
            ("startsequence", "<sequence> <exptime> <count> <cameras> [<combined>]", self.startsequence),
            ("stopsequence", "<sequence>", self.stopsequence),
            ("inusesequence", "<sequence>", self.inusesequence),
            ("inusecamera", "<camera>", self.inusecamera),
            ("insertVisit", "<visit>", self.insertVisit),
            ("setCentroidParams", "[<nmin>] [<thresh>] [<deblend>]", self.setCentroidParams),
            ("setImageParams", "", self.setImageParams),
        ]

        # Define typed command arguments for the above commands.
        self.keys = keys.KeysDictionary(
            "agcc_agcc",
            (1, 1),
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

    def ping(self, cmd) -> None:
        """Reply to a ``ping`` command to confirm liveness.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmd.respond("text='I am AG camera actor'")
        cmd.finish()

    def reconnect(self, cmd) -> None:
        """Reload the camera controller and reconnect the AG cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        self.actor.reloadCamera(cmd, self.actor.actorConfig)
        cmd.inform('text="AG cameras connected!"')
        cmd.finish()

    def status(self, cmd) -> None:
        """Report the actor version and per-camera status.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        self.actor.sendVersionKey(cmd)
        self.actor.camera.sendStatusKeys(cmd)

        cmd.inform('text="Present!"')
        cmd.finish()

    def setOrGetVisit(self, cmd) -> int:
        """Return the ``visit`` from the command keys, or fetch one from gen2.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.

        Returns
        -------
        int
            The PFS visit identifier in use for this command.
        """

        self.cmd = cmd
        cmdKeys = cmd.cmd.keywords

        # When we start a new visit, always reset frame counter.
        self.frameSeq = 0
        if "visit" in cmdKeys:
            self.visit = cmdKeys["visit"].values[0]
        else:
            ret = self.actor.cmdr.call(
                actor="gen2", cmdStr="getVisit caller=agcc", forUserCmd=cmd, timeLim=15.0
            )
            if ret.didFail:
                raise RuntimeError("getNextFilename failed getting a visit number in 15s!")
            self.visit = self.actor.models["gen2"].keyVarDict["visit"].valueList[0]

        return self.visit

    def insertVisit(self, cmd) -> None:
        """Insert a row into the ``pfs_visit`` OpDB table.

        Parameters
        ----------
        cmd : object
            The parsed tron command object; must carry a ``visit`` keyword.
        """
        cmdKeys = cmd.cmd.keywords
        visit = cmdKeys["visit"].values[0]
        database.writeVisitToDB(visit)
        cmd.finish()

    def shutterOps(self, cmd) -> None:
        """Open or close the shutter on the requested cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object; carries the ``open``/``close``
            sub-command and an optional ``cameras`` list.
        """
        cmdKeys = cmd.cmd.keywords
        shutterMode = cmdKeys[0].name
        cams = []
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
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

        if shutterMode == "open":
            self.actor.camera.openShutter(cmd, cams)
        if shutterMode == "close":
            self.actor.camera.closeShutter(cmd, cams)

        cmd.finish()

    def expose(self, cmd) -> None:
        """Take an exposure on the requested cameras.

        Recognised command keywords include ``test``/``dark``/``object``,
        ``visit``, ``exptime``, ``cameras``, ``combined`` (0/1),
        ``centroid`` (0/1), ``cMethod``, ``threadDelay`` and ``tecOFF``.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmdKeys = cmd.cmd.keywords
        expType = cmdKeys[0].name
        visit = self.setOrGetVisit(cmd)
        self.actor.logger.info(f"Starting exposure of type {expType} for pfs_visit_id={visit}")

        # Ask gen2 updating the telescope status
        self.actor.cmdr.call(actor="gen2", cmdStr=f"updateTelStatus caller=agcc visit={visit}", timeLim=5.0)

        if "exptime" in cmdKeys:
            expTime = cmdKeys["exptime"].values[0]
        else:
            expTime = 0.0

        combined = True
        if "combined" in cmdKeys:
            if cmdKeys["combined"].values[0] == 0:
                combined = False

        centroid = False
        if "centroid" in cmdKeys:
            if cmdKeys["centroid"].values[0] == 1:
                centroid = True

        cMethod = "sep"
        if "cMethod" in cmdKeys:
            cMethod = cmdKeys["cMethod"].values[0]

        if "threadDelay" in cmdKeys:
            threadDelay = cmdKeys["threadDelay"].values[0]
        else:
            threadDelay = 0.0

        if "tecOFF" in cmdKeys:
            tecOFF = True
        else:
            tecOFF = False

        cmd.inform(f'text="TEC OFF status = {tecOFF}"')
        cmd.inform(f'text="Setting threading delay of {threadDelay} ms"')

        self.actor.logger.info(
            f"Setting image params: {visit=} {expTime=} {combined=} "
            f"{centroid=} {cMethod=} {threadDelay=} {tecOFF=}"
        )
        self.setImageParams(cmd)

        magFit = self.iParms["magFit"]
        cmd.inform(f'text="read magFit = {magFit}"')

        cams = []
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
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
        self.actor.camera.expose(
            cmd,
            expTime,
            expType,
            cams,
            combined,
            centroid,
            visit,
            self.cParms,
            cMethod,
            self.iParms,
            threadDelay=threadDelay,
            tecOFF=tecOFF,
        )

    def abort(self, cmd) -> None:
        """Abort the current exposure on the requested cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmdKeys = cmd.cmd.keywords
        cams = []
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
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

    def setframe(self, cmd) -> None:
        """Set the exposure area on the requested cameras.

        Command keywords: ``cameras``, ``bx``, ``by``, ``cx``, ``cy``,
        ``sx``, ``sy``.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmdKeys = cmd.cmd.keywords
        cams = []
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
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

        if "bx" in cmdKeys:
            bx = cmdKeys["bx"].values[0]
        else:
            bx = 0
        if "by" in cmdKeys:
            by = cmdKeys["by"].values[0]
        else:
            by = 0
        if "cx" not in cmdKeys or "cy" not in cmdKeys or "sx" not in cmdKeys or "sy" not in cmdKeys:
            cmd.error('text="reqired parameters (cx,cy,sx,sy) missing"')
            cmd.fail()
            return
        cx = cmdKeys["cx"].values[0]
        cy = cmdKeys["cy"].values[0]
        sx = cmdKeys["sx"].values[0]
        sy = cmdKeys["sy"].values[0]

        self.actor.camera.setframe(cmd, cams, bx, by, cx, cy, sx, sy)

    def resetframe(self, cmd) -> None:
        """Reset the exposure area to the full frame on the requested cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmdKeys = cmd.cmd.keywords
        cams = []
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
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

    def setmode(self, cmd) -> None:
        """Set the readout mode (``0`` = 4 MHz, ``1`` = 500 kHz).

        Parameters
        ----------
        cmd : object
            The parsed tron command object; must carry a ``mode`` keyword.
        """

        cmdKeys = cmd.cmd.keywords
        mode = cmdKeys["mode"].values[0]

        cams = []
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
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

    def getmode(self, cmd) -> None:
        """Get the current readout mode on the requested cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmdKeys = cmd.cmd.keywords
        cams = []
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
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

    def getmodestring(self, cmd) -> None:
        """Get the human-readable readout mode strings from the first camera.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        self.actor.camera.getmodestring(cmd)

    def settemperature(self, cmd) -> None:
        """Set the CCD temperature on one or more cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object; must carry a ``temperature``
            keyword and may carry an optional ``cameras`` list.
        """

        cmdKeys = cmd.cmd.keywords
        temperature = cmdKeys["temperature"].values[0]
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
            cmd.inform(f'text="Setting temerature for AG cameras = {camList}"')

            for cam in camList:
                n = int(cam) - 1
                cmd.inform(f'text="Setting camera AG{n + 1} to {temperature}"')
                self.actor.camera.setcamtemperature(cmd, n, temperature)
        else:
            self.actor.camera.settemperature(cmd, temperature)
        cmd.finish('text="Setting camera TEC finished!"')

    def setregions(self, cmd) -> None:
        """Set regions of interest for a given camera.

        Parameters
        ----------
        cmd : object
            The parsed tron command object; must carry ``camera`` and
            ``regions`` keywords.
        """

        cmdKeys = cmd.cmd.keywords
        camid = cmdKeys["camera"].values[0]
        regions = cmdKeys["regions"].values[0]
        self.actor.camera.setregions(cmd, camid, regions)

    def startsequence(self, cmd) -> None:
        """Deprecated no-op; the exposure sequence feature has been removed.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmd.finish('text="startsequence is deprecated and no longer supported; command ignored"')

    def stopsequence(self, cmd) -> None:
        """Deprecated no-op; the exposure sequence feature has been removed.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmd.finish('text="stopsequence is deprecated and no longer supported; command ignored"')

    def inusesequence(self, cmd) -> None:
        """Deprecated no-op; the exposure sequence feature has been removed.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmd.finish('text="inusesequence is deprecated and no longer supported; command ignored"')

    def inusecamera(self, cmd) -> None:
        """Report whether a given camera is currently in use.

        Parameters
        ----------
        cmd : object
            The parsed tron command object; must carry a ``camera`` keyword.
        """

        cmdKeys = cmd.cmd.keywords
        cam_id = cmdKeys["camera"].values[0] - 1
        if cam_id < 0 or cam_id >= nCams:
            cmd.fail('text="camera id error: %d"' % (cam_id + 1))
            return
        stat = self.actor.camera.camera_stat(cam_id)
        cmd.respond('stat_cam%d="%s"' % (cam_id + 1, stat))
        cmd.finish()

    def setCentroidParams(self, cmd) -> None:
        """Load centroid parameters from the config file, with keyword overrides.

        Parameters
        ----------
        cmd : object or None
            The parsed tron command object whose keywords may override the
            defaults. If ``None``, defaults are loaded without a reply.
        """

        self.cParms = centroid.getCentroidParams(cmd)
        thresh = self.cParms["thresh"]
        deblend = self.cParms["deblend"]
        nmin = self.cParms["nmin"]
        if cmd is not None:
            cmd.finish(f'text="centroid parameters set thresh/deblend/nmin = {thresh} {deblend} {nmin}"')

    def setImageParams(self, cmd) -> None:
        """Load per-camera instrumental parameters from the config file.

        Parameters
        ----------
        cmd : object or None
            The parsed tron command object. Currently only used for logging.
        """
        self.actor.logger.info(f"Setting image parameters: {cmd=}")
        self.iParms = centroid.getImageParams(cmd)
