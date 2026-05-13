#!/usr/bin/env python

from importlib import reload

from actorcore.Actor import Actor

from agccActor import camera


class AgccActor(Actor):
    """Tron actor controlling the PFS AG (Auto Guider) cameras."""

    def __init__(
        self,
        name: str,
        productName: str | None = None,
        configFile: str | None = None,
        debugLevel: int = 30,
    ):
        """Construct the AGCC actor and connect to the cameras.

        Parameters
        ----------
        name : str
            The actor name registered with the tron hub.
        productName : str, optional
            EUPS product name, forwarded to :class:`actorcore.Actor`.
        configFile : str, optional
            Path to the actor configuration file.
        debugLevel : int, optional
            Initial debug log level.
        """
        # This sets up the connections to/from the hub, the logger, and the twisted reactor.
        #
        Actor.__init__(self, name, productName=productName, configFile=configFile, modelNames=("gen2"))

        print(f"   actorConfig: {self.actorConfig}")

        # We will actually use a allocator with "global" sequencing
        self.exposureID = 0

        self.connectCamera(self.bcast, self.actorConfig)

    def reloadCamera(self, cmd, config: dict, doFinish: bool = True) -> None:
        """Close existing cameras and create a fresh :class:`Camera` controller.

        Parameters
        ----------
        cmd : object
            A tron command object used for status replies.
        config : dict
            Actor configuration dictionary passed to :class:`Camera`.
        doFinish : bool, optional
            Reserved for API compatibility.
        """
        # first, delete all camera object
        if hasattr(self, "camera"):
            self.camera.closeCamera()
            del self.camera
        self.camera = camera.Camera(config)
        self.camera.sendStatusKeys(cmd)

    def connectCamera(self, cmd, config: dict, doFinish: bool = True) -> None:
        """Reload the ``camera`` module and connect to the cameras.

        Parameters
        ----------
        cmd : object
            A tron command object used for status replies.
        config : dict
            Actor configuration dictionary passed to :class:`Camera`.
        doFinish : bool, optional
            Reserved for API compatibility.
        """
        reload(camera)
        self.camera = camera.Camera(config)
        self.camera.sendStatusKeys(cmd)


def main() -> None:
    """Entry point: start the AGCC tron actor."""
    actor = AgccActor("agcc", productName="agccActor")
    actor.run()


if __name__ == "__main__":
    main()
