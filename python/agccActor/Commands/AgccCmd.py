#!/usr/bin/env python

import opscore.protocols.keys as keys
import opscore.protocols.types as types
from actorcore.Command import Command

from agccActor import centroid, database
from agccActor.main import AgccActor

nCams = 6


class AgccCmd(object):
    """Command vocabulary for the AGCC tron actor.

    Registers the command grammar and keyword dictionary used by the
    actor parser, and provides one handler per command.
    """

    def __init__(self, actor: AgccActor):
        """Register the command vocabulary and keyword dictionary.

        Parameters
        ----------
        actor : object
            The owning :class:`AgccActor` instance.
        """
        self.cmd = None
        self.visit = None
        self.instrumentalParams = None
        self.centroidingParams = None
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
            ("setCentroidParams", "[<nmin>] [<thresh>] [<deblend>]", self.reloadParams),
            ("setImageParams", "", self.reloadParams),
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
        # initialize centroid and image parameters
        self.reloadParams(None)

    def ping(self, cmd: Command) -> None:
        """Reply to a ``ping`` command to confirm liveness.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmd.respond("text='I am AG camera actor'")
        cmd.finish()

    def reconnect(self, cmd: Command) -> None:
        """Reload the camera controller and reconnect the AG cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        self.actor.reloadCamera(cmd, self.actor.actorConfig)
        cmd.inform('text="AG cameras connected!"')
        cmd.finish()

    def status(self, cmd: Command) -> None:
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

    def lookup_cameras(self, cmd: Command, defaultToRunning: bool = False) -> list[int]:
        """Parse the ``cameras`` keyword to get a list of 0-indexed camera IDs.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        defaultToRunning : bool, default False
            If True and the ``cameras`` keyword is missing, default to the
            currently running cameras. Otherwise, default to all cameras.

        Returns
        -------
        list of int
            A list of 0-indexed camera IDs.
        """
        cmdKeys = cmd.cmd.keywords
        if "cameras" in cmdKeys:
            camList = cmdKeys["cameras"].values[0]
            return [int(cam) - 1 for cam in camList]

        if defaultToRunning:
            cams = self.actor.camera.runningCameras()
            cmd.inform(f'text="found cameras: {cams}"')
            return cams

        return list(range(nCams))

    def setOrGetVisit(self, cmd: Command) -> int:
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

    def insertVisit(self, cmd: Command) -> None:
        """Insert a row into the ``pfs_visit`` OpDB table.

        Parameters
        ----------
        cmd : object
            The parsed tron command object; must carry a ``visit`` keyword.
        """
        cmdKeys = cmd.cmd.keywords
        visit = cmdKeys["visit"].values[0]
        try:
            database.writeVisitToDB(visit)
        except Exception as e:
            cmd.fail(f'text="insertVisit DB error for visit={visit}: {e}"')
            return
        cmd.finish()

    def shutterOps(self, cmd: Command) -> None:
        """Open or close the shutter on the requested cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object; carries the ``open``/``close``
            sub-command and an optional ``cameras`` list.
        """
        cmdKeys = cmd.cmd.keywords
        shutterMode = cmdKeys[0].name
        cams = self.lookup_cameras(cmd)

        if shutterMode == "open":
            self.actor.camera.openShutter(cmd, cams)
        if shutterMode == "close":
            self.actor.camera.closeShutter(cmd, cams)

        cmd.finish()

    def expose(self, cmd: Command) -> None:
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

        # Ask gen2 to update the telescope status; fail fast if it doesn't succeed.
        ret = self.actor.cmdr.call(
            actor="gen2", cmdStr=f"updateTelStatus caller=agcc visit={visit}", timeLim=5.0
        )
        if ret.didFail:
            cmd.fail(f'text="updateTelStatus failed for visit={visit}; cannot write exposure record"')
            return

        if "exptime" in cmdKeys:
            expTime = cmdKeys["exptime"].values[0]
        else:
            expTime = 0.0

        combined = True
        if "combined" in cmdKeys:
            if cmdKeys["combined"].values[0] == 0:
                combined = False

        do_centroid = False
        if "centroid" in cmdKeys:
            if cmdKeys["centroid"].values[0] == 1:
                do_centroid = True

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
            f"{do_centroid=} {cMethod=} {threadDelay=} {tecOFF=}"
        )

        magFit = self.instrumentalParams["magFit"]
        cmd.inform(f'text="read magFit = {magFit}"')

        cams = self.lookup_cameras(cmd, defaultToRunning=True)

        # Report TEC before taking exposure
        self.actor.camera.reportTEC(cmd)
        cmd.inform(f'text="pfs_visit_id: {visit}"')
        self.actor.camera.expose(
            cmd,
            expTime,
            expType,
            cams,
            combined,
            do_centroid,
            visit,
            self.centroidingParams,
            cMethod,
            self.instrumentalParams,
            threadDelay=threadDelay,
            tecOFF=tecOFF,
        )

    def abort(self, cmd: Command) -> None:
        """Abort the current exposure on the requested cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cams = self.lookup_cameras(cmd)

        self.actor.camera.abort(cmd, cams)
        cmd.finish('text="Last exposure aborted!"')

    def setframe(self, cmd: Command) -> None:
        """Set the exposure area on the requested cameras.

        Command keywords: ``cameras``, ``bx``, ``by``, ``cx``, ``cy``,
        ``sx``, ``sy``.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmdKeys = cmd.cmd.keywords
        cams = self.lookup_cameras(cmd)

        if "bx" in cmdKeys:
            bx = cmdKeys["bx"].values[0]
        else:
            bx = 0
        if "by" in cmdKeys:
            by = cmdKeys["by"].values[0]
        else:
            by = 0
        if "cx" not in cmdKeys or "cy" not in cmdKeys or "sx" not in cmdKeys or "sy" not in cmdKeys:
            cmd.error('text="required parameters (cx,cy,sx,sy) missing"')
            cmd.fail('text="required parameters (cx,cy,sx,sy) missing"')
            return
        cx = cmdKeys["cx"].values[0]
        cy = cmdKeys["cy"].values[0]
        sx = cmdKeys["sx"].values[0]
        sy = cmdKeys["sy"].values[0]

        self.actor.camera.setframe(cmd, cams, bx, by, cx, cy, sx, sy)

    def resetframe(self, cmd: Command) -> None:
        """Reset the exposure area to the full frame on the requested cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cams = self.lookup_cameras(cmd)

        self.actor.camera.resetframe(cmd, cams)

    def setmode(self, cmd: Command) -> None:
        """Set the readout mode (``0`` = 4 MHz, ``1`` = 500 kHz).

        Parameters
        ----------
        cmd : object
            The parsed tron command object; must carry a ``mode`` keyword.
        """

        cmdKeys = cmd.cmd.keywords
        mode = cmdKeys["mode"].values[0]

        cams = self.lookup_cameras(cmd)

        self.actor.camera.setmode(cmd, mode, cams)

    def getmode(self, cmd: Command) -> None:
        """Get the current readout mode on the requested cameras.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cams = self.lookup_cameras(cmd)

        self.actor.camera.getmode(cmd, cams)

    def getmodestring(self, cmd: Command) -> None:
        """Get the human-readable readout mode strings from the first camera.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        self.actor.camera.getmodestring(cmd)

    def settemperature(self, cmd: Command) -> None:
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
            cams = self.lookup_cameras(cmd)
            cmd.inform(f'text="Setting temperature for AG cameras = {cmdKeys["cameras"].values[0]}"')

            for n in cams:
                cmd.inform(f'text="Setting camera AG{n + 1} to {temperature}"')
                self.actor.camera.setcamtemperature(cmd, n, temperature)
        else:
            self.actor.camera.settemperature(cmd, temperature)
        cmd.finish('text="Setting camera TEC finished!"')

    def setregions(self, cmd: Command) -> None:
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

    def startsequence(self, cmd: Command) -> None:
        """Deprecated no-op; the exposure sequence feature has been removed.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmd.finish('text="startsequence is deprecated and no longer supported; command ignored"')

    def stopsequence(self, cmd: Command) -> None:
        """Deprecated no-op; the exposure sequence feature has been removed.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmd.finish('text="stopsequence is deprecated and no longer supported; command ignored"')

    def inusesequence(self, cmd: Command) -> None:
        """Deprecated no-op; the exposure sequence feature has been removed.

        Parameters
        ----------
        cmd : object
            The parsed tron command object.
        """

        cmd.finish('text="inusesequence is deprecated and no longer supported; command ignored"')

    def inusecamera(self, cmd: Command) -> None:
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

    def reloadParams(self, cmd: Command | None = None) -> None:
        """Load centroid and instrumental parameters from the config file.

        Parameters
        ----------
        cmd : object or None
            The parsed tron command object whose keywords may override the
            defaults. If ``None``, defaults are loaded without a reply.
        """

        self.centroidingParams, self.instrumentalParams = centroid.getParams(cmd)
        if cmd is not None:
            thresh = self.centroidingParams["thresh"]
            deblend = self.centroidingParams["deblend"]
            nmin = self.centroidingParams["nmin"]
            cmd.finish(
                f'text="Parameters reloaded. Centroid thresh/deblend/nmin = {thresh}/{deblend}/{nmin}"'
            )
