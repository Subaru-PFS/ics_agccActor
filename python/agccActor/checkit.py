import centroidTools as ct
import dbRoutinesAGCC as dbRoutinesAGCC
from astropy.io.fits import getdata

cParm = ct.getCentroidParams([])
image = getdata("/Users/karr/test1.fits")

centroids = ct.getCentroids(image, cParm)

dbRoutinesAGCC.writeCentroidsToDB(centroids, 100, 1)
