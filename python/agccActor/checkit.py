

import centroidTools as ct
from astropy.io.fits import getdata
import numpy as np
import dbRoutinesAGCC as dbRoutinesAGCC
import pandas as pd

cParm=ct.getCentroidParams([])
image=getdata("/Users/karr/test1.fits")

centroids=ct.getCentroids(image,cParm)

dbRoutinesAGCC.writeCentroidsToDB(centroids,100,1)
