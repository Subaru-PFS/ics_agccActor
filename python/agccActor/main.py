#!/usr/bin/env python

"""AGCC actor entrypoint.

This module defines the top-level actor wrapper used by tron to initialize
camera control and command handling.
"""

from __future__ import annotations

from importlib import reload
from typing import Any

from actorcore.Actor import Actor

from agccActor import camera


class AgccActor(Actor):
    """Top-level AGCC actor.

    Parameters
    ----------
    name : str
        Actor name used by tron.
    productName : str | None, optional
        Product name used by actorcore configuration lookup.
    configFile : str | None, optional
        Explicit actor configuration file path.
    debugLevel : int, optional
        Debug level value accepted for compatibility.
    """

    def __init__(
        self,
        name: str,
        productName: str | None = None,
        configFile: str | None = None,
        debugLevel: int = 30,
    ) -> None:
        # This sets up the connections to/from the hub, the logger, and the twisted reactor.
        #
        Actor.__init__(self, name, productName=productName, configFile=configFile, modelNames=("gen2"))

        print(f"   actorConfig: {self.actorConfig}")

        # We will actually use a allocator with "global" sequencing
        self.exposureID = 0

        self.connectCamera(self.bcast, self.actorConfig)

    def reloadCamera(self, cmd: Any, config: dict[str, Any], doFinish: bool = True) -> None:
        """Recreate camera connections.

        Parameters
        ----------
        cmd : Any
            Command object used for status reporting.
        config : dict[str, Any]
            Actor configuration dictionary.
        doFinish : bool, optional
            Kept for API compatibility.
        """
        # first, delete all camera object
        if hasattr(self, "camera"):
            self.camera.closeCamera()
            del self.camera
        self.camera = camera.Camera(config)
        self.camera.sendStatusKeys(cmd)

    def connectCamera(self, cmd: Any, config: dict[str, Any], doFinish: bool = True) -> None:
        """Connect camera objects from configuration.

        Parameters
        ----------
        cmd : Any
            Command object used for status reporting.
        config : dict[str, Any]
            Actor configuration dictionary.
        doFinish : bool, optional
            Kept for API compatibility.
        """
        reload(camera)
        self.camera = camera.Camera(config)
        self.camera.sendStatusKeys(cmd)


def main() -> None:
    """Run the AGCC actor process."""
    actor = AgccActor("agcc", productName="agccActor")
    actor.run()


if __name__ == "__main__":
    main()
