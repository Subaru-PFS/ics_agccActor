import os

import numpy as np
import glob
import os
from opdb import opdb
import pandas as pd

def connectToDB(username='pfs', hostname = 'db-ics', dbname="opdb", password='2394f4s3d', port=5432)
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

