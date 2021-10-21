
#import os
import pandas as pd
import numpy as np
#import matplotlib.pyplot as plt
#import pathlib
#import sys

#import pandas as pd
#from scipy.stats import sigmaclip
#import copy
#import dbRoutinesAGCC 

#from scipy.stats import sigmaclip
#rootPath=os.path.join(os.environ['ICS_MHS_ROOT'])
#dbPath=os.path.join(rootPath,"devel/spt_operational_databasepython/opdb-0.1-py3.8.egg/")
#sys.path.insert(1, dbPath)

from opdb import opdb


def connectToDB(hostname='117.56.225.230',port='5432',dbname='opdb',username='pfs',passwd=None):

    """
    connect to DB
    """
    
    db = opdb.OpDB(hostname, port, dbname, username, passwd)
    db.connect()
    
    return db
    #return None


def writeVisitToDB(pfsVisitId):

    db=connectToDB()
    
    df = pd.DataFrame({'pfs_visit_id': [pfsVisitId], 'pfs_visit_description': ['']})
    #db.insert('pfs_visit', df)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print('pfs_visit', df)

    #try:
    #    db.insert('pfs_visit', df)
    #except:
    #    pass
    

def writeExposureToDB(visitId,exposureId):

    db=connectToDB()
    df = pd.DataFrame({'pfs_visit_id': [visitId], 'agc_exposure_id': [exposureId]})
    #db.insert('agc_exposure', df)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print('agc_exposure', df)

            
def writeCentroidsToDB(centroids,visitId,exposureId,cameraId):

    """
    write the centroids to the database
    table=mcs_data
    variables=spot_id,mcs_center_x_pix,mcs_center_y_pix
              mcs_second_moment_x_pix,mcs_second_moment_y_pix,
              mcs_second_moment_xy_pix,bgvalue,peakvalue
    """
    db=connectToDB()


    sz=centroids.shape
    frame=np.zeros((sz[0],14))


    #create array of frameIDs (same for all spots)
    visitIds=np.repeat(visitId,sz[0]).astype('int')
    exposureIds=np.repeat(exposureId,sz[0]).astype('int')
    cameraIds=np.repeat(cameraId,sz[0]).astype('int')
    #make a data frame
    frame[:,0]=visitIds
    frame[:,1]=exposureIds
    frame[:,2]=cameraIds
    frame[:,3:]=centroids[:,0:11]


    columns = ['pfs_visit_id','agc_exposure_id','agc_camera_id','spot_id','centroid_x_pix','centroid_y_pix','peak_pixel_x_pix','peak_pixel_y_pix','central_image_moment_20_pix','central_image_moment_02_pix','central_image_moment_11_pix','peak_intensity','image_moment_00_pix','background']

    df=pd.DataFrame(frame,columns=columns)
    
    #db.insert("agc_data",df)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print("agc_data", df)
