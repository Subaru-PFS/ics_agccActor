
import numpy as np
import matplotlib.pylab as plt

import astropy.units as u
from astropy.coordinates import SkyCoord
from astroquery.gaia import Gaia
from astropy.io import fits

import galsimRoutines as gs
from scipy.stats import sigmaclip
import centroid as centroid
from astropy.io.fits import getdata


def getCat(xCent,yCent,xSize,ySize,xScale,yScale):
    
    """
    retrieve 
    """
    coord = SkyCoord(ra=xCent, dec=yCent, unit=(u.degree, u.degree), frame='icrs')
    width = u.Quantity(xSize, u.deg)
    height = u.Quantity(ySize, u.deg)
    Gaia.ROW_LIMIT = 1000
    r = Gaia.query_object_async(coordinate=coord, width=width, height=height)
    ra=(r['ra']-xCent)*xScale
    dec=(r['dec']-yCent)*yScale

    xPos=(r['ra']-xCent)*1072/xSize+1072/2
    yPos=(r['dec']-yCent)*1037/ySize+1037/2
    flux=r['phot_g_mean_flux']
    mag=r['phot_g_mean_mag']
    return xPos,yPos,flux,mag

def fluxToADU(mag):
    
    flux=3.631e-20*10**(-0.4*mag)
    #flux2=10**(-0.4*(mag-25.7))
    t=0.1
    
    aTel=4*np.pi*(8.2e2)**2
    nu=3e8/600e-9
    qe=0.9
    fact=0.88
    gain=1.3
    h=6.6261e-27

    ADU=flux*gain*fact*qe*nu*aTel*t/(h*nu)
    return ADU
    
def convertToFits():

    noStep=np.loadtxt("InputFiles/AG1_PSF_0.8arcsec_NoStep.txt",skiprows=18)
    fits.writeto("noStep.fits",noStep/noStep.sum(),clobber=True)
    withStep=np.loadtxt("InputFiles/AG1_PSF_0.8arcsec_WithStep.txt",skiprows=18)
    fits.writeto("withStep.fits",withStep/withStep.sum(),clobber=True)

def downloadCats(xCent,yCent,xSize,ySize,xScale,yScale):

    #get Catalogue
    xPos,yPos,flux,mag=getCat(xCent,yCent,xSize,ySize,xScale,yScale)
    f=fluxToADU(mag)

    #write to file
    dFile="sim_"+str(int(xCent))+"_"+str(int(yCent))+".dat"
    aa=open(dFile,"w")
        for i in range(nSource[ii]):
            print(xPos[i],yPos[i],int(f[i]),mag[i],file=aa)
    aa.close()

def simImages(xCent,yCent,suffix,fFact):
    
    dFile="sim_"+str(int(xCent))+"_"+str(int(yCent))+".dat"
    oFile="sim_"+str(int(xCent))+"_"+str(int(yCent))+suff+".fits"

    xPos,yPos,f,mag=loadCat(xCent,yCent)
    f=f*fFact

    gs.simImage("20210513_AG6_centroid_images/agcc_s0_20210514_0435382.fits","noStep.fits","withStep.fits",xPos,yPos,f,oFile)

def loadCat(xCent,yCent):
    
    dFile="sim_"+str(int(xCent))+"_"+str(int(yCent))+".dat"

    aa=np.lodtxt(dFile)
    xPos=aa[:,0]
    yPos=aa[:,1]
    f=aa[:,2]
    mag=aa[:,3]

    return xPos,yPos,f,mag


    
