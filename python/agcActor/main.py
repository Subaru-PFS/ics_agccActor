#!/usr/bin/env python

from actorcore.Actor import Actor
import camera

class AgcActor(Actor):
    def __init__(self, name, productName=None, configFile=None, debugLevel=30):
        # This sets up the connections to/from the hub, the logger, and the twisted reactor.
        #
        Actor.__init__(self, name, 
                       productName=productName, 
                       configFile=configFile)

        # We will actually use a allocator with "global" sequencing
        self.exposureID = 0
        
        self.connectCamera(self.bcast, self.config)
        
    def connectCamera(self, cmd, config, doFinish=True):
        reload(camera)
        self.camera = camera.Camera(config)
        self.camera.sendStatusKeys(cmd)

#
# To work

def main():
    actor = AgcActor('agc', productName='agcActor')
    actor.run()

if __name__ == '__main__':
    main()

