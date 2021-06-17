
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pathlib
import sys

import pandas as pd
from scipy.stats import sigmaclip
import copy

from scipy.stats import sigmaclip
rootPath=os.path.join(os.environ['ICS_MHS_ROOT'])
dbPath=os.path.join(rootPath,"devel/spt_operational_databasepython/opdb-0.1-py3.8.egg/")
sys.path.insert(1, dbPath)

from opdb import opdb


def connectToDB(hostname='117.56.225.230',port='5432',dbname='opdb',username='pfs',passwd=None):

    """
    connect to DB
    """
    
    db = opdb.OpDB(hostname, port, dbname, username, passwd)
    db.connect()
    
    return db


def writeVisitToDB(nFrame):

    db=connectToDB(hostname='localhost',port='5432',dbname='opdb',username='karr',passwd=None)

    
    df = pd.DataFrame({'pfs_visit_id': [nFrame], 'pfs_visit_description': ['']})

    try:
        db.insert('pfs_visit', df)
    except:
        pass
    



def writeExposureToDB(visitId,cameraId):

    db=connectToDB(hostname='localhost',port='5432',dbname='opdb',username='karr',passwd=None)
    df = pd.DataFrame({'pfs_visit_id': [visitId], 'agc_exposure_id': [visitId*100+cameraId], 'agc_camera_id': [cameraId]})
    db.insert('agc_exposure', df)

            
def writeCentroidsToDB(centroids,visitId,cameraID):

    """
    write the centroids to the database
    table=mcs_data
    variables=spot_id,mcs_center_x_pix,mcs_center_y_pix
              mcs_second_moment_x_pix,mcs_second_moment_y_pix,
              mcs_second_moment_xy_pix,bgvalue,peakvalue
    """


    db=connectToDB(hostname='localhost',port='5432',dbname='opdb',username='karr',passwd=None)

    #get size of array
    sz=centroids.shape
    
    #create array of frameIDs (same for all spots)
    visitIds=np.repeat(visitId,sz[0]).astype('int')
    #make a data frame
    frame=np.zeros((sz[0],15))
    frame[:,0]=visitIds
    frame[:,1]=visitIds*100+np.repeat(cameraID,sz[0]).astype('int')
    frame[:,2]=np.repeat(cameraID,sz[0]).astype('int')
    frame[:,3:]=centroids
    #column names
    columns=['pfs_visit_id','agc_exposure_id','agc_camera_id','spot_id','centroid_x_pix','centroid_y_pix','peak_pixel_x_pix','peak_pixel_y_pix','central_image_moment_20_pix','central_image_moment_02_pix','central_image_moment_11_pix','peak_intensity','image_moment_00_pix','background','flags']

    df=pd.DataFrame(frame,columns=columns)
    db.insert("agc_data",df)

def writeExposuretoDB(centroids,visitId,cameraID):

    """
    write the centroids to the database
    table=mcs_data
    variables=spot_id,mcs_center_x_pix,mcs_center_y_pix
              mcs_second_moment_x_pix,mcs_second_moment_y_pix,
              mcs_second_moment_xy_pix,bgvalue,peakvalue
    """


    db=connectToDB(hostname='localhost',port='5432',dbname='opdb',username='karr',passwd=None)

    #get size of array
    sz=centroids.shape
    
    #create array of frameIDs (same for all spots)
    visitIds=np.repeat(visitId,sz[0]).astype('int')
    #make a data frame
    frame=np.zeros((sz[0],15))
    frame[:,0]=visitIds
    frame[:,1]=visitIds*100+np.repeat(cameraID,sz[0]).astype('int')
    frame[:,2]=np.repeat(cameraID,sz[0]).astype('int')
    frame[:,3:]=centroids
    #column names
    columns=['pfs_visit_id','agc_exposure_id','agc_camera_id','spot_id','centroid_x_pix','centroid_y_pix','peak_pixel_x_pix','peak_pixel_y_pix','central_image_moment_20_pix','central_image_moment_02_pix','central_image_moment_11_pix','peak_intensity','image_moment_00_pix','background','flags']

    df=pd.DataFrame(frame,columns=columns)
    db.insert("agc_data",df)
