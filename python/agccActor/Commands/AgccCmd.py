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
            ('expose', '@(test|dark|object) [<exptime>] [<cameras>] [<combined>] [<centroid>]', self.expose),
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
                                        keys.Key("centroid", types.Int(), help="0/1: if 1 do centroid else don't"),
                                        )
