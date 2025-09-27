import multiprocessing
import threading
import writeFits
import photometry
import os
import time
from opdb import opdb

import dbRoutinesAGCC as dbRoutinesAGCC

class Exposure(threading.Thread):
    exp_lock = threading.Lock()
    n_busy = 0

    def __init__(self, cams, expTime_ms, dflag, cParms, iParms, visitId, cMethod, 
                 cmd = None, combined = False, centroid = False, seq_id = -1, 
                 threadDelay=None, tecOFF=False):
        
        """ Run exposure command

        Args:
           cams        - list of active cameras
           expTime_ms  - the exposure time in ms
           dflag       - true for dark exposure
           cmd         - a Command object to report to. Ignored if None.
           combined    - Multiple FITS files/Single FITS file
           centroid    - True if do centroid else don't
           seq_id      - Sequence id

        Returns:
           - NULL

        Keys:
           stat_cam[1-6]
        """
        threading.Thread.__init__(self, daemon=False)
        self.cams = cams
        self.expTime_ms = expTime_ms
        self.dflag = dflag
        self.cmd = cmd
        self.combined = combined
        self.centroid = centroid
        self.visitId = visitId
        self.cParms = cParms
        self.iParms = iParms
        self.seq_id = seq_id
        self.cMethod = cMethod

        # update the exposure time in cParms

        self.cParms['expTime']=expTime_ms/1000

        self.tecOFFtemp = 20

        if tecOFF is True:
            self.tecOFF = True
        else:
            self.tecOFF = False

        # setting defalut time delay before next exposure thread.
        if threadDelay is None:
            self.timeDelay = 0.0
        else:
            self.timeDelay = threadDelay/1000

        # Getting last entry of agc_exposure_id from DB
        db=opdb.OpDB(hostname='db-ics', port=5432,dbname='opdb',
                        username='pfs')
        
        query = db.bulkSelect('agc_exposure','select agc_exposure_id from agc_exposure ORDER BY '
                      f'agc_exposure_id DESC LIMIT 1')
        last_nframe = query['agc_exposure_id'].values[0]
        self.nframe = last_nframe + 1
        self.cmd.inform(f'text="Getting agc_exposure_id = {self.nframe} from opDB"')
        
        # get nframe keyword, unique for each exposure
        path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
        #path = os.path.join('/data/raw', time.strftime('%Y-%m-%d', time.gmtime()), 'agcc')

        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isdir(path):
            os.makedirs(path, 0o755)
        filename = os.path.join(path, 'nframe.txt')

        with Exposure.exp_lock:
            #if os.path.isfile(filename):
            #    with open(filename, 'r') as f:
            #        self.nframe = int(f.read()) + 1
            #else:
            #    self.nframe = 1
            if os.path.isfile(filename):
                with open(filename, 'w') as f:
                    f.write(str(self.nframe))
            self.cmd.inform(f'text="Recording agc_exposure_id = {self.nframe} to {filename}"')
        dbRoutinesAGCC.writeExposureToDB(self.visitId,self.nframe, expTime_ms/1000.0)

    def run(self):
        # check if any camera is available
        if len(self.cams) <= 0:
            if self.cmd:
                self.cmd.warn('text="No available cameras"')
                self.cmd.finish()
            return

        with Exposure.exp_lock:
            Exposure.n_busy += len(self.cams)
            if self.cmd:
                self.cmd.inform('agc_exposing=%d' % Exposure.n_busy)

        thrs = []
        for cam in self.cams:
            self.cmd.inform(f'text="Applying time delay of {self.timeDelay} second on Cam {cam.devsn}"')
            time.sleep(self.timeDelay)
            
            if self.tecOFF is True:
                targetTemp = cam.temp
                self.cmd.inform(f'text="AGCC sets CCD temp = {targetTemp}"')

                self.cmd.inform(f'text="Turing off TEC by setting to {self.tecOFFtemp}C on Cam {cam.devsn}"')
                cam.setTemperature(self.tecOFFtemp)

            thr = threading.Thread(target=self.expose_thr, args=(cam,))
            thr.start()
            thrs.append(thr)
        self.cmd.debug(f'text="done starting {len(thrs)} exposure threads"')

        for thr in thrs:
            thr.join()
        self.cmd.debug('text="done joining exposure threads"')

        with Exposure.exp_lock:
            Exposure.n_busy -= len(self.cams)
            if self.cmd:
                self.cmd.inform('agc_exposing=%d' % Exposure.n_busy)
                self.cmd.inform('agc_frameid=%d' % self.nframe)

        if self.combined and self.cams[0].getTotalTime() > 0:
            writeFits.wfits_combined(self.cmd, self.visitId, self.cams, self.nframe, self.seq_id)
        
        
        if self.tecOFF is True:
            '''
                Turning TEC on!
            '''
            for cam in self.cams:
                self.cmd.inform(f'text="Turing on TEC to {targetTemp}C"')
                cam.setTemperature(targetTemp)
        
        if self.cmd and self.seq_id < 0:
            self.cmd.finish()

    def expose_thr(self, cam, multiproc=True):
        """ Concurrent exposure thread for camera readouts """
        cam_id = cam.agcid + 1
        if self.cmd:
            self.cmd.inform(f'agc{cam_id:d}_stat=BUSY')

        try:
            cam.setExpTime(self.expTime_ms)
        except Exception as e:
            if self.cmd:
                self.cmd.warn(f'text="AGC[{cam_id}]: set exposure time error: {e}"')
            return

        try:
            cam.expose(dark=self.dflag)
        except Exception as e:
            if self.cmd:
                self.cmd.warn(f'text="AGC[{cam_id}]: exposure error: {e}"')
            return

        try:
            tread = cam.getTotalTime()
        except Exception as e:
            if self.cmd:
                self.cmd.warn(f'text="AGC[{cam_id}]: readout error in getTotalTime: {e}"')
            return

        if self.cmd:
            if tread > 0:
                self.cmd.inform(f'text="AGC[{cam_id:d}]: Retrieve camera data in {tread:.2f}s"')
            else:
                self.cmd.inform(f'text="AGC[{cam_id:d}]: Exposure aborted"')
            self.cmd.inform(f'agc{cam_id:d}_stat=READY')

        spots = None
        if tread > 0:
            if self.centroid:
                if multiproc:
                    cam.in_queue.put(cam.data)
                    cam.in_queue.put(cam.agcid)
                    cam.in_queue.put(self.cParms)
                    cam.in_queue.put(self.iParms)
                    cam.in_queue.put(self.cMethod)
                    try:
                        spots = cam.out_queue.get()
                    except Exception as e:
                        self.cmd.warn(f'text="AGC[{cam_id}]: photometry multiprocessing error with photometry: {e}"')
                else:
                    try:
                        spots = photometry.measure(cam.data,cam.agcid,self.cParms,self.iParms,self.cMethod)
                    except Exception as e:
                        self.cmd.warn(f'text="AGC[{cam_id}]: photometry error: {e}"')
                        spots = None

                cam.spots = spots

                # Writing to database when spot number is larger than zero
                if spots is not None and len(spots) > 0:
                    if self.cmd:
                        self.cmd.inform(f'text="AGC[{cam_id:d}]: find {len(spots):d} objects"')
                        self.cmd.inform(f'text="AGC[{cam_id:d}]: wrote centroids to database"')
                        aa=spots['estimated_magnitude']
                        self.cmd.inform(f'text="AGC[{cam_id:d}]: estimated mags = {aa}"')
                        
                    dbRoutinesAGCC.writeCentroidsToDB(spots,self.visitId, self.nframe,cam.agcid)
                else:
                    self.cmd.inform(f'text="AGC[{{cam_id:d}}]: found no objects, skipping DB writing"')
            else:
                cam.spots = spots

            if not self.combined:
                writeFits.wfits(self.cmd, self.visitId, cam, self.nframe)
