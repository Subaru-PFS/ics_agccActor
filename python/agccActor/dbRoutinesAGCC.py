import psycopg2
import pandas as pd
import numpy as np
from opdb import opdb
import datetime

import logging

logger = logging.getLogger('agcc')
logger.setLevel(logging.INFO)

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
                    'agc_exptime': exptime,
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

            
def writeCentroidsToDB(result, visitId, exposureId, cameraId):
    """
    Write the centroids to the database in bulk.
    Table: agc_data
    Variables: spot_id, mcs_center_x_pix, mcs_center_y_pix,
               mcs_second_moment_x_pix, mcs_second_moment_y_pix,
               mcs_second_moment_xy_pix, bgvalue, peakvalue
    """
    sz = result.shape

    # Create array of frameIDs, etc. (same for all spots)
    visitIds = np.repeat(visitId, sz[0]).astype('int')
    exposureIds = np.repeat(exposureId, sz[0]).astype('int')
    cameraIds = np.repeat(cameraId, sz[0]).astype('int')

    # Turn the record array into a pandas DataFrame
    df = pd.DataFrame(result)

    # Add the extra fields
    df['agc_exposure_id'] = exposureIds
    df['agc_camera_id'] = cameraIds
    df['spot_id'] = np.arange(0, sz[0]).astype('int')

    logger.info(f"Table is prepared for pfs_visit_id={visitId} agc_exposure_id={exposureId} camera={cameraId}.")

    # Replace NaN values with None for compatibility with psycopg2
    df = df.where(pd.notnull(df), None)

    # Prepare the bulk insert query
    insert_query = """
        INSERT INTO agc_data (
            agc_exposure_id, agc_camera_id, spot_id, image_moment_00_pix, 
            centroid_x_pix, centroid_y_pix, central_image_moment_20_pix,
            central_image_moment_11_pix, central_image_moment_02_pix,
            peak_pixel_x_pix, peak_pixel_y_pix, peak_intensity, background,
            estimated_magnitude, flags
        ) VALUES %s
    """

    # Convert DataFrame rows to tuples for bulk insert
    values = [
        (
            row['agc_exposure_id'], row['agc_camera_id'], row['spot_id'],
            row['image_moment_00_pix'], row['centroid_x_pix'], row['centroid_y_pix'],
            row['central_image_moment_20_pix'], row['central_image_moment_11_pix'],
            row['central_image_moment_02_pix'], row['peak_pixel_x_pix'],
            row['peak_pixel_y_pix'], row['peak_intensity'], row['background'],
            row['estimated_magnitude'], row['flags']
        )
        for _, row in df.iterrows()
    ]

    # Execute the bulk insert
    try:
        db = psycopg2.connect(host='db-ics', dbname='opdb', user='pfs')
        with db as conn:
            with conn.cursor() as curs:
                psycopg2.extras.execute_values(curs, insert_query, values)
        logger.info("Bulk insert completed successfully.")
    except Exception as e:
        logger.error(f"Error during bulk insert: {e}")
