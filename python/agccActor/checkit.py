
from astropy.io import fits
import centroidTools as ct
import numpy as np
import dbRoutinesAGCC as dbr
data=fits.getdata("/Users/karr/test1.fits")

spots=ct.getCentroids(data)

dbr.writeVisitToDB(86)
dbr.writeExposureToDB(86,1)

dbr.writeCentroidsToDB(spots,86,1)
