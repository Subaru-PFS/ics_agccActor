import os
import yaml
from astropy.io.fits import getdata
from astropy.io.fits import writeto

import numpy as np
import glob
from scipy.stats import sigmaclip
import matplotlib.pylab as plt
import sep
from scipy.ndimage import gaussian_filter
from importlib import reload
import glob
import centroidTools as ct
from astropy.io import fits
import os
from opdb import opdb
import pandas as pd

def run(files,iParms,i):
                        
    spotDtype = np.dtype(dict(names=['image_moment_00_pix', 'centroid_x_pix', 'centroid_y_pix', 'central_image_moment_20_pix', 'central_image_moment_11_pix', 'central_image_moment_02_pix', 'peak_pixel_x_pix', 'peak_pixel_y_pix', 'peak_intensity', 'background', 'flags'],
                          formats=['f4', 'f4', 'f4', 'f4', 'f4' ,'f4', 'i2', 'i2', 'f4', 'f4', 'i2']))

    thresh=8

    for fName in files:
        with fits.open(fName) as hdul:
            print(fName,i)
            data = hdul[i].data
            frameNo = hdul[i].header['frameid']

            oFile=str(int(frameNo))+"_"+str(int(i))+".npy"
            if os.path.exists(oFile):
               print("dup",frameNo,fName)
            if(data is not None):
                if len(data.shape) > 1: 
                    result=ct.getCentroidsSep(data,iParms,spotDtype,1,thresh)
                    np.save(oFile,result)
                else:
                    pass
            else:
                passs

def connectToDB(hostname='localhost',port='5432',dbname='opdb',username='karr',passwd=None):

    db = opdb.OpDB(hostname, port, dbname, username, passwd)
    db.connect()

    return db

def repop():

    files=glob.glob("*.npy")
    db=connectToDB()
    for fName in files:
        visitId=int(fName.split("_")[0])
        frameId=int(visitId)
        agcid=int(fName.split("_")[1].split(".")[0])
        
        exposureId=1

        print("A ",visitId, exposureId)
        df = pd.DataFrame({'pfs_visit_id': [visitId], 'agc_exposure_id': [frameId]})

        try:
            db.insert('agc_exposure', df)
        except:
            pass
        
        result=np.load(fName)
        
        sz=result.shape
        df=pd.DataFrame(result)
        l=len(result)
        df['agc_exposure_id']=np.repeat(frameId,l)
        df['agc_camera_id']=np.repeat(agcid,l)
        df['spot_id']=np.arange(0,sz[0]).astype('int')

        db.insert('agc_data', df)
  

cmd=None
fileName=os.path.join(os.environ['ICS_AGCCACTOR_DIR'],'etc','agcCamParm.yaml')

with open(fileName, 'r') as inFile:
    iParms=yaml.safe_load(inFile)

                
inDir="/Users/karr/AllScience/Data/AG/AAASome/"

#allFiles = glob.glob("/Users/karr/Science/Data/PFS/AG/AAASome/*.fits")
#print(iParms['1'])
#for i in range(1,7):
#    run(allFiles,iParms,i)

repop()

