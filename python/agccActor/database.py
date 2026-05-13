import datetime
import logging

import numpy as np
import pandas as pd
from pfs.utils.database import opdb

logger = logging.getLogger('agcc')
logger.setLevel(logging.INFO)


def getNextAgcExposureId(db: opdb.OpDB | None = None) -> int:
    """Get the next available AGC exposure identifier.

    Parameters
    ----------
    db : opdb.OpDB, optional
        The database connection object. If not provided, a new connection is created.

    Returns
    -------
    int
        The next available AGC exposure identifier.
    """
    db = db or opdb.OpDB()
    result = db.query_scalar('SELECT MAX(agc_exposure_id) + 1 AS next_id FROM agc_exposure')
    return result if result is not None else 0


def writeVisitToDB(pfsVisitId: int, db: opdb.OpDB | None = None) -> None:
    """Write the visit number to the pfs_visit table.

    Parameters
    ----------
    pfsVisitId : int
        The PFS visit identifier.
    db : opdb.OpDB, optional
        The database connection object. If not provided, a new connection is created.
    """
    db = db or opdb.OpDB()
    db.insert_kw('pfs_visit', pfs_visit_id=pfsVisitId, pfs_visit_description='')


def writeExposureToDB(visitId: int, exposureId: int, exptime: float, db: opdb.OpDB | None = None) -> None:
    """Write exposure information to the agc_exposure table.

    This includes telescope information and environmental conditions.

    Parameters
    ----------
    visitId : int
        The PFS visit identifier.
    exposureId : int
        The AGC exposure identifier.
    exptime : float
        The exposure time in seconds.
    db : opdb.OpDB, optional
        The database connection object. If not provided, a new connection is created.
    """
    db = db or opdb.OpDB()

    # Getting telescope information
    teleInfo = db.query_series(
        'select pfs_visit_id, altitude, azimuth, insrot, adc_pa, m2_pos3 '
        'FROM tel_status WHERE pfs_visit_id = :pfs_visit_id ORDER BY status_sequence_id DESC limit 1',
        params={'pfs_visit_id': visitId}
    )

    if teleInfo is None:
        logger.error(f"No telescope status found for pfs_visit_id={visitId}. Cannot write exposure record.")
        raise RuntimeError(f"No telescope status found for pfs_visit_id={visitId}.")

    obsCond = db.query_series(
        'select pfs_visit_id, outside_temperature, outside_pressure, outside_humidity '
        'FROM env_condition WHERE pfs_visit_id = :pfs_visit_id ORDER BY status_sequence_id DESC limit 1',
        params={'pfs_visit_id': visitId}
    )

    if obsCond is None:
        logger.error(f"No environmental conditions found for pfs_visit_id={visitId}. Cannot write exposure record.")
        raise RuntimeError(f"No environmental conditions found for pfs_visit_id={visitId}.")

    cols = {'pfs_visit_id': visitId,
            'agc_exposure_id': exposureId,
            'agc_exptime': exptime,
            'altitude': teleInfo['altitude'],
            'azimuth': teleInfo['azimuth'],
            'insrot': teleInfo['insrot'],
            'adc_pa': teleInfo['adc_pa'],
            'm2_pos3': teleInfo['m2_pos3'],
            'outside_temperature': obsCond['outside_temperature'],
            'outside_pressure': obsCond['outside_pressure'],
            'outside_humidity': obsCond['outside_humidity'],
            'taken_at': datetime.datetime.now(),
            'measurement_algorithm': 'SEP',
            'version_actor': 'git',
            'version_instdata': 'git',
            }

    try:
        db.insert_kw('agc_exposure', **cols)
    except Exception as e:
        logger.error(
            f"Failed to insert agc_exposure record for pfs_visit_id={visitId} agc_exposure_id={exposureId}: {e}"
        )
        raise


def writeCentroidsToDB(result: np.ndarray, visitId: int, exposureId: int, cameraId: int, db: opdb.OpDB | None = None
                       ) -> None:
    """Write the centroids to the database in bulk.

    Table: agc_data
    Variables: spot_id, mcs_center_x_pix, mcs_center_y_pix,
               mcs_second_moment_x_pix, mcs_second_moment_y_pix,
               mcs_second_moment_xy_pix, bgvalue, peakvalue

    Parameters
    ----------
    result : numpy.ndarray
        The array of centroiding results.
    visitId : int
        The PFS visit identifier.
    exposureId : int
        The AGC exposure identifier.
    cameraId : int
        The AGC camera identifier.
    db : opdb.OpDB, optional
        The database connection object. If not provided, a new connection is created.
    """
    db = db or opdb.OpDB()
    num_centroids = result.shape[0]

    # Create array of frameIDs, etc. (same for all spots)
    exposureIds = np.repeat(exposureId, num_centroids).astype('int')
    cameraIds = np.repeat(cameraId, num_centroids).astype('int')

    # Turn the record array into a pandas DataFrame
    df = pd.DataFrame(result)

    # Add the extra fields
    df['agc_exposure_id'] = exposureIds
    df['agc_camera_id'] = cameraIds
    df['spot_id'] = np.arange(0, num_centroids).astype('int')

    logger.info(f"Table is prepared for pfs_visit_id={visitId} agc_exposure_id={exposureId} camera={cameraId}.")

    db.insert_dataframe('agc_data', df=df)
