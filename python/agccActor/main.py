#!/usr/bin/env python

from actorcore.Actor import Actor
import camera
from importlib import reload
from twisted.internet import reactor

class AgccActor(Actor):
    def __init__(self, name, productName=None, configFile=None, debugLevel=30):
        # This sets up the connections to/from the hub, the logger, and the twisted reactor.
        #
        Actor.__init__(self, name, 
                       productName=productName, 
                       configFile=configFile)

        # We will actually use a allocator with "global" sequencing
        self.exposureID = 0
        self.monitorPeriod = 0
        self.statusLoopCB = self.statusLoop
        
        self.connectCamera(self.bcast, self.config)
        
    def connectCamera(self, cmd, config, doFinish=True):
        reload(camera)
        self.camera = camera.Camera(config)
        self.camera.sendStatusKeys(cmd)

    def statusLoop(self):
        try:
            self.callCommand("gettemperature")
        except:
            pass

        if self.monitorPeriod > 0:
            reactor.callLater(self.monitorPeriod, self.statusLoopCB)

    def monitor(self, period, cmd=None):
        """ Arrange for 'status' to be called """

        running = self.monitorPeriod > 0
        self.monitorPeriod = period

        if (not running) and period > 0:
            if cmd:
                cmd.warn('text="starting %gs loop for monitoring temperature"' % (period))
            self.statusLoopCB()
        elif cmd:
            cmd.warn('text="adjusted temperature monitor loop to %gs"' % (self.monitorPeriod))

#
# To work

def main():
    actor = AgccActor('agcc', productName='agccActor')
    actor.run()

if __name__ == '__main__':
    main()

