import psycopg2
import pandas as pd
import numpy as np
from opdb import opdb
import datetime

def connectToDB(hostname='db-ics',port='5432',dbname='opdb',username='pfs',passwd=None):

    """
    connect to DB
    """
    
    db = opdb.OpDB(hostname=hostname, port=port, dbname=dbname, username=username)
    db.connect()
    
    return db


def writeVisitToDB(pfsVisitId):

    """
    Temporary routine for testing: write visit number to pfs_visit. In operation this will be 
    done from a higher level
    
    """

    db=connectToDB()
    

    df = pd.DataFrame({'pfs_visit_id': [pfsVisitId], 'pfs_visit_description': ['']})
    #pd.set_option('display.max_columns', None)
    #pd.set_option('display.width', None)
    #print('pfs_visit', df)

    try:
        db.insert('pfs_visit', df)
    except:
        pass
    

def writeExposureToDB(visitId,exposureId, exptime):

    """
    Temporary routine for testing: write to agcc_exposure so we can write to agcc_data. 
    In real operation will be done from a higher level
    
    """


    db=connectToDB()

    # Getting telescope information
    teleInfo = db.bulkSelect('tel_status','select pfs_visit_id, altitude, azimuth, insrot, adc_pa, m2_pos3 FROM tel_status '
                        f'ORDER BY pfs_visit_id DESC limit 1')

    obsCond = db.bulkSelect('env_condition','select pfs_visit_id, outside_temperature, outside_pressure, outside_humidity '
                        f' FROM env_condition ORDER BY pfs_visit_id DESC limit 1')

    df = pd.DataFrame({'pfs_visit_id': visitId, 
                    'agc_exposure_id': exposureId,
                    'altitude': teleInfo['altitude'],
                    'azimuth': teleInfo['azimuth'],
                    'insrot': teleInfo['insrot'],
                    'adc_pa': teleInfo['adc_pa'],
                    'm2_pos3': teleInfo['m2_pos3'],
                    'outside_temperature': obsCond['outside_temperature'],
                    'outside_pressure' : obsCond['outside_pressure'],
                    'outside_humidity': obsCond['outside_humidity'],
                    'taken_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'measurement_algorithm': 'SEP',
                    'version_actor': 'git',
                    'version_instdata': 'git',
                    })

    db.insert('agc_exposure', df)
    #pd.set_option('display.max_columns', None)
    #pd.set_option('display.width', None)
    #print('agc_exposure', df)

            
def writeCentroidsToDB(result,visitId,exposureId,cameraId):

    """
    write the centroids to the database
    table=mcs_data
    variables=spot_id,mcs_center_x_pix,mcs_center_y_pix
              mcs_second_moment_x_pix,mcs_second_moment_y_pix,
              mcs_second_moment_xy_pix,bgvalue,peakvalue
    """
    import logging

    logger = logging.getLogger('agcc')
    logger.setLevel(logging.INFO)
    
    sz=result.shape

    # create array of frameIDs, etc (same for all spots)
    visitIds=np.repeat(visitId,sz[0]).astype('int')
    exposureIds=np.repeat(exposureId,sz[0]).astype('int')
    cameraIds=np.repeat(cameraId,sz[0]).astype('int')

    # turn the record array into a pandas df
    df=pd.DataFrame(result)

    # add the extra fields
    #df['pfs_visit_id']=visitIds
    df['agc_exposure_id']=exposureIds
    df['agc_camera_id']=cameraIds
    df['spot_id']=np.arange(0,sz[0]).astype('int')

    logger.info(f"Table is prepared.")

    db = psycopg2.connect(host='db-ics', dbname='opdb', user='pfs')
    
    dbString = f'''INSERT INTO agc_data (agc_exposure_id, agc_camera_id, spot_id, image_moment_00_pix, 
        centroid_x_pix, centroid_y_pix, central_image_moment_20_pix,central_image_moment_11_pix,
        central_image_moment_02_pix,peak_pixel_x_pix, peak_pixel_y_pix, peak_intensity, background,
        estimated_magnitude, flags)  VALUES'''
    

    for i in range(sz[0]):
        cmdString = f"""{dbString}({df['agc_exposure_id'].values[i]}, {df['agc_camera_id'].values[i]}, {df['spot_id'].values[i]}, 
            {df['image_moment_00_pix'].values[i]}, {df['centroid_x_pix'].values[i]}, {df['centroid_y_pix'].values[i]},
            {df['central_image_moment_20_pix'].values[i]}, {df['central_image_moment_11_pix'].values[i]},
            {df['central_image_moment_02_pix'].values[i]}, 
            {df['peak_pixel_x_pix'].values[i]}, {df['peak_pixel_y_pix'].values[i]}, 
            {df['peak_intensity'].values[i]}, {df['background'].values[i]},
            {df['estimated_magnitude'].values[i]}, {df['flags'].values[i]})"""
    

        logger.info(f'{cmdString}')
    
        with db as conn:
            with conn.cursor() as curs:
                curs.execute(cmdString)
