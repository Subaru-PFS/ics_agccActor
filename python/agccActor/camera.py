import numpy
from datetime import datetime
import fli_camera
from twisted.internet import reactor
import thread
import astropy.io.fits as pyfits
import os
import photometry

nCams = 6
POLL_TIME = 0.02
SEQ_IDLE = 0
SEQ_RUNNING = 1
SEQ_ABORT = 2
CAM_NONEXISTENT = 0
CAM_READY = 1
CAM_BUSY = 2

class Camera(object):
	""" Subaru PFI AG cameras """

	def __init__(self, config):
		""" connect to AG cameras """

		self.numberOfCamera = fli_camera.numberOfCamera()
		self.cams = [None, None, None, None, None, None]
		self.cam_stat = [CAM_NONEXISTENT] * nCams
		self.seq_stat = [SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE]
		self.seq_count = [0, 0, 0, 0, 0, 0]
		self.seq_filename = ["", "", "", "", "", ""]
		temp = float(config.get('agcc', 'temperature'))
		for n in range(self.numberOfCamera):
			cam = fli_camera.Camera(n)
			cam.open()
			for k in range(nCams):
				if cam.devsn == config.get('agcc', 'cam' + str(k + 1)):
					self.cams[k] = cam
					self.cam_stat[k] = CAM_READY
					cam.agcid = k
					cam.setTemperature(temp)
					cam.regions = ((0, 0, 0), (0, 0, 0))
					break
			else:
				cam.close()

	def sendStatusKeys(self, cmd):
		""" Send our status keys to the given command. """ 

		cmd.inform('text="Number of AG cameras = %d"' % self.numberOfCamera)
		for n in range(nCams):
			if self.cams[n] != None:
				if self.cams[n].isReady():
					tempstr = '%5.1f' % self.cams[n].getTemperature()
				else:
					tempstr = '<%5.1f>' % self.cams[n].temp
				cmd.inform('text="[%d] %s SN=%s status=%s temp=%s regions=%s bin=(%d,%d) expArea=%s"'
						   % (n + 1, self.cams[n].devname, self.cams[n].devsn,
						   self.cams[n].getStatusStr(), tempstr, self.cams[n].regions,
						   self.cams[n].hbin, self.cams[n].vbin, self.cams[n].expArea))

	def expose(self, cmd, expTime, expType, cams, combined):
		""" Generate an 'exposure' image.

		Args:
		   cmd      - a Command object to report to. Ignored if None.
		   expTime  - the exposure time. 
		   expType  - ("dark", "object", "test")
		   cams     - list of active cameras [1-6]
		   combined - Multiple FITS files/Single FITS file

		Returns:
		   - NULL

		Keys:
		   stat_cam[1-6]
		"""

		# check if any camera is available
		cams_available = []
		for n in cams:
			if self.cams[n] != None:
				cams_available.append(n)
		if len(cams_available) <= 0:
			if cmd:
				cmd.warn('text="No available cameras"')
				cmd.finish()
			return

		# check if all cameras are ready
		for n in cams_available:
			if not self.cams[n].isReady():
				if cmd:
					cmd.fail('text="camera busy, command ignored"')
				return

		if not expType:
			expType = 'test'
		for n in cams_available:
			self.cam_stat[n] = CAM_BUSY
			if cmd:
				cmd.inform('stat_cam%d="BUSY"' % (n + 1))

		if expType == 'test':
			for n in cams_available:
				self.cams[n].expose_test()
				if not combined:
					self.wfits(cmd, self.cams[n])
			if combined:
				self.wfits_combined(cmd, cams_available)
			for n in cams_available:
				self.cam_stat[n] = CAM_READY
				if cmd:
					tread = self.cams[n].tend - self.cams[n].tstart
					cmd.diag('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
					cmd.inform('stat_cam%d="READY"' % (n + 1))
					cmd.finish()
		else:
			expTime_ms = int(expTime * 1000)
			if expType == 'dark':
				dflag = True
			else:
				dflag = False

			for n in cams_available:
				thread.start_new_thread(expose_call, (self.cams[n], expTime_ms, dflag))
			reactor.callLater(POLL_TIME, self.expose_bottom, cmd, cams_available, cams_available, combined)

	def expose_bottom(self, cmd, cams, cams_check, combined):
		""" Wait for expose finishes and return the message """

		cams_busy = []
		cam_abort = False
		for n in cams_check:
			if not self.cams[n].isReady():
				cams_busy.append(n)
			elif self.cams[n].tend > 0:
				self.cam_stat[n] = CAM_READY
				if cmd:
					tread = self.cams[n].tend - self.cams[n].tstart
					cmd.diag('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
					cmd.inform('stat_cam%d="READY"' % (n + 1))
				if not combined:
					self.wfits(cmd, self.cams[n])
			else:
				self.cam_stat[n] = CAM_READY
				cam_abort = True
				if cmd:
					cmd.diag('text="AGC[%d]: Exposure aborted"' % (n + 1))
					cmd.inform('stat_cam%d="READY"' % (n + 1))
		if len(cams_busy) > 0:
			reactor.callLater(POLL_TIME, self.expose_bottom, cmd, cams, cams_busy, combined)
		else:
			if combined and not cam_abort:
				self.wfits_combined(cmd, cams)
			if cmd:
				cmd.finish()

	def wfits(self, cmd, cam):
		"""Write the image to a FITS file"""

		path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
		path = os.path.expandvars(os.path.expanduser(path))
		if not os.path.isdir(path):
			os.makedirs(path, 0o755)
		filename = os.path.join(path, 'agcc_c%d_%s.fits' % \
		       (cam.agcid + 1, cam.timestamp))

		if(cam.data.size == 0):
			print "No image available"
			return
		hdu = pyfits.PrimaryHDU(cam.data)
		hdr = hdu.header
		hdr.update('DATE', cam.timestamp, 'exposure begin date')
		hdr.update('INSTRUME', cam.devname, 'this instrument')
		hdr.update('SERIAL', cam.devsn, 'serial number')
		hdr.update('EXPTIME', cam.exptime, 'exposure time (ms)')
		hdr.update('VBIN', cam.vbin, 'vertical binning')
		hdr.update('HBIN', cam.hbin, 'horizontal binning')
		hdr.update('CCD-TEMP', cam.getTemperature(), 'CCD temperature')
		if(cam.dark != 0):
			hdr.update('SHUTTER', 'CLOSE', 'shutter status')
		else:
			hdr.update('SHUTTER', 'OPEN', 'shutter status')
		hdr.update('CCDAREA', '[%d:%d,%d:%d]' % cam.expArea, 'image area')
		hdu.writeto(filename, clobber=True, checksum=True)
		cam.filename = filename
		if cmd:
			cmd.inform('fits_cam%d="%s"' % (cam.agcid + 1, filename))

	def wfits_combined(self, cmd, cams, seq_id = -1):
		"""Write the images to a FITS file"""

		path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
		path = os.path.expandvars(os.path.expanduser(path))
		if not os.path.isdir(path):
			os.makedirs(path, 0o755)
		if len(cams) > 0:
			mtimestamp = self.cams[cams[0]].timestamp
		else:
			now = datetime.now()
			mtimestamp = now.strftime("%Y%m%d%H%M%S%f")[:-5]
		filename = os.path.join(path, 'agcc_s%d_%s.fits' % (seq_id + 1, mtimestamp))

		hdulist = pyfits.HDUList([pyfits.PrimaryHDU()])
		for n in range(6):
			extname = "cam%d" % (n + 1)
			if not n in cams:
				hdulist.append(pyfits.ImageHDU(name=extname))
				continue
			cam = self.cams[n]
			hdu = pyfits.ImageHDU(cam.data, name=extname)
			hdr = hdu.header
			hdr.update('DATE', cam.timestamp, 'exposure begin date')
			hdr.update('INSTRUME', cam.devname, 'this instrument')
			hdr.update('SERIAL', cam.devsn, 'serial number')
			hdr.update('EXPTIME', cam.exptime, 'exposure time (ms)')
			hdr.update('VBIN', cam.vbin, 'vertical binning')
			hdr.update('HBIN', cam.hbin, 'horizontal binning')
			hdr.update('CCD-TEMP', cam.getTemperature(), 'CCD temperature')
			if(cam.dark != 0):
				hdr.update('SHUTTER', 'CLOSE', 'shutter status')
			else:
				hdr.update('SHUTTER', 'OPEN', 'shutter status')
			hdr.update('CCDAREA', '[%d:%d,%d:%d]' % cam.expArea, 'image area')
			hdr.update('REGION1', '[%d:%d,%d]' % cam.regions[0], 'region 1')
			hdr.update('REGION2', '[%d:%d,%d]' % cam.regions[1], 'region 2')
			hdulist.append(hdu)

		hdulist.writeto(filename, checksum=True, clobber=True)
		if seq_id >= 0:
			photometry.measure(hdulist)
			self.seq_filename[seq_id] = filename
			if cmd:
				cmd.inform('fits_seq%d="%s"' % (seq_id + 1, filename))
				cmd.inform('stat_seq%d="%s"' % (seq_id + 1, "0, 0, 0, 0, 0, 0"))

	def abort(self, cmd, cams):
		""" Abort current exposure

		Args:
		   cmd     - a Command object to report to. Ignored if None.
		   cams    - list of active cameras [1-8]
		"""

		for n in cams:
			if self.cams[n] != None and not self.cams[n].isReady():
				cmd.diag('text="Send abort command to AGC[%d]"' % (n + 1))
				self.cams[n].cancelExposure()

	def setframe(self, cmd, cams, bx, by, cx, cy, sx, sy):
		""" set exposure area

		Args:
		   cmd     - a Command object to report to. Ignored if None.
		   cams    - list of active cameras [1-8]
		   bx,by   - binning size
		   cx,cy   - corner coordinate
		   sx,sy   - exposure area size
		"""

		for n in cams:
			if self.cams[n] != None and not self.cams[n].isReady():
				if cmd:
					cmd.fail('text="camera busy, command ignored"')
				return

		for n in cams:
			if self.cams[n] != None:
				if cmd:
					cmd.diag('text="Send setframe command to AGC[%d]"' % (n + 1))
				if bx > 0:
					self.cams[n].setHBin(bx)
				if by > 0:
					self.cams[n].setHBin(by)
				self.cams[n].setFrame(cx, cy, sx, sy)
		if cmd:
			cmd.inform('text="Camera expose area set"')
			cmd.finish()

	def resetframe(self, cmd, cams):
		""" reset exposure area

		Args:
		   cmd     - a Command object to report to. Ignored if None.
		   cams    - list of active cameras [1-8]
		"""

		for n in cams:
			if self.cams[n] != None and not self.cams[n].isReady():
				if cmd:
					cmd.fail('text="camera busy, command ignored"')
				return

		for n in cams:
			if self.cams[n] != None:
				if cmd:
					cmd.diag('text="Send resetframe command to AGC[%d]"' % (n + 1))
				self.cams[n].resetFrame()
		if cmd:
			cmd.inform('text="Camera expose area reset"')
			cmd.finish()

	def setmode(self, cmd, mode, cams):
		""" Set camera readout mode

		Args:
		   cmd     - a Command object to report to. Ignored if None.
		   mode    - readout mode
		   cams    - list of active cameras [1-8]
		"""

		cams_available = []
		for n in cams:
			if self.cams[n] != None:
				if not self.cams[n].isReady():
					if cmd:
						cmd.fail('text="camera busy, command ignored"')
					return
				else:
					cams_available.append(n)
		for n in cams_available:
			thread.start_new_thread(self.cams[n].setMode, (mode,))
			if cmd:
				cmd.diag('text="Send setmode(%d) command to AGC[%d]"' % (mode, n + 1))
		if cmd:
			reactor.callLater(POLL_TIME, self.setmode_bottom, cmd, cams_available)

	def setmode_bottom(self, cmd, cams):
		""" Wait for setmode finishes and return the message """

		cams_busy = []
		for n in cams:
			if not self.cams[n].isReady():
				cams_busy.append(n)
		if len(cams_busy) > 0:
			reactor.callLater(POLL_TIME, self.setmode_bottom, cmd, cams_busy)
		elif cmd:
			cmd.inform('text="Camera setmode command done"')
			cmd.finish()

	def getmode(self, cmd, cams):
		""" Get camera readout mode

		Args:
		   cmd     - a Command object to report to. Ignored if None.
		   cams    - list of active cameras [1-8]
		"""

		for n in cams:
			if self.cams[n] != None and not self.cams[n].isReady():
				if cmd:
					cmd.fail('text="camera busy, command ignored"')
				return
		for n in cams:
			if self.cams[n] != None:
				mode = self.cams[n].getMode()
				if cmd:
					cmd.respond('text="AGC[%d] readout mode: %d"' % (n + 1, mode))
		cmd.inform('text="Camera getmode command done"')
		cmd.finish()

	def getmodestring(self, cmd):
		""" Get mode string from the first available camera

		Args:
		   cmd     - a Command object to report to. Ignored if None.
		"""

		for n in range(nCams):
			if self.cams[n] != None and self.cams[n].isReady():
				s0 = self.cams[n].getModeString(0)
				s1 = self.cams[n].getModeString(1)
				if cmd:
					cmd.respond('text="mode 0: %s"' % (s0))
					cmd.respond('text="mode 1: %s"' % (s1))
					cmd.inform('text="Camera getmodestring command done"')
					cmd.finish()
				return
		if cmd:
			cmd.fail('text="camera busy or none attached, command ignored"')

	def settemperature(self, cmd, temp):
		""" Set CCD temperature

		Args:
		   cmd     - a Command object to report to. Ignored if None.
		   temp    - CCD temperature
		"""

		busy = False
		for n in range(nCams):
			if self.cams[n] != None:
				if self.cams[n].isReady():
					self.cams[n].setTemperature(temp)
				else:
					busy = True
					if cmd:
						cmd.warn('text="Camera [%d] is busy"' % n)
		if cmd:
			if busy:
				cmd.fail('text="Camera settemperature command abort"')
			else:
				cmd.inform('text="Camera settemperature command done"')
				cmd.finish()

	def setregions(self, cmd, camid, regions_str):
		""" Set CCD regions of interested

		Args:
		   cmd         - a Command object to report to. Ignored if None.
		   camid       - Camera ID
		   regions_str - Regions of interest to set
		"""

		pars = regions_str.split(',')
		if len(pars) == 3:
			# only one region
			self.cams[camid].regions = ((pars[0], pars[1], pars[2]), (0, 0, 0))
		elif len(pars) == 6:
			# two regions
			self.cams[camid].regions = ((pars[0], pars[1], pars[2]), (pars[3], pars[4], pars[5]))
		else:
			# wrong number of parameters
			if cmd:
				cmd.fail('text="setregions command failed, invalid parameter: %s"' % regions_str)
			return

		if cmd:
			cmd.inform('text="setregions command done"')
			cmd.finish()

	def startsequence(self, cmd, seq_id, expTime, count, cams, combined):
		""" Start a exposure sequence

		Args:
		   cmd      - a Command object to report to. Ignored if None.
		   seq_id   - Sequence ID
		   expTime  - exposure time
		   count    - number of exposures
		   cams     - list of active cameras [1-6]
		"""

		cams_available = []
		for n in cams:
			if self.cams[n] != None and self.cams[n].isReady():
				cams_available.append(n)
			elif cmd:
				cmd.warn('text="Camera [%d] is not available"' % n)
		if len(cams_available) <= 0:
			if cmd:
				cmd.fail('text="No usable camera"')
			return

		if self.seq_stat[seq_id] != SEQ_IDLE:
			if cmd:
				cmd.fail('text="Sequence ID %d in used"' % (seq_id + 1))
			return
		self.seq_stat[seq_id] = SEQ_RUNNING
		self.seq_count[seq_id] = 0
		expTime_ms = int(expTime * 1000)
		if cmd:
			cmd.inform('inused_seq%d="YES"' % (seq_id + 1))
		for n in cams_available:
			if cmd:
				cmd.inform('stat_cam%d="BUSY"' % (n + 1))
			self.cam_stat[n] = CAM_BUSY
			thread.start_new_thread(expose_call, (self.cams[n], expTime_ms, False))
		reactor.callLater(POLL_TIME, self.startsequence_bottom, cmd, seq_id, expTime_ms, \
		                  count, cams_available, cams_available, combined)

	def startsequence_bottom(self, cmd, seq_id, expTime_ms, count, cams, cams_check, combined):
		""" Handling an image sequence """

		cams_busy = []
		for n in cams_check:
			if not self.cams[n].isReady():
				cams_busy.append(n)
			elif self.cams[n].tend > 0:
				if cmd:
					tread = self.cams[n].tend - self.cams[n].tstart
					cmd.diag('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
				if not combined:
					self.wfits(cmd, self.cams[n])
			else:
				if cmd:
					cmd.diag('text="AGC[%d]: Exposure aborted"' % (n + 1))
		if self.seq_stat[seq_id] == SEQ_ABORT:
			if len(cams_busy) > 0:
				self.abort(cmd, cams_busy)
			reactor.callLater(POLL_TIME, self.startsequence_abort, cmd, seq_id, cams, cams_busy)
			return
		if len(cams_busy) > 0:
			reactor.callLater(POLL_TIME, self.startsequence_bottom, cmd, seq_id, expTime_ms, \
			                  count, cams, cams_busy, combined)
		else:
			if combined:
				self.wfits_combined(cmd, cams, seq_id)
			self.seq_count[seq_id] += 1
			if cmd:
				cmd.inform('text="Sequence [%d] count [%d] done"' % \
				           (seq_id + 1, self.seq_count[seq_id]))
			if self.seq_count[seq_id] == count:
				self.seq_stat[seq_id] = SEQ_IDLE
				for n in cams:
					self.cam_stat[n] = CAM_READY
					if cmd:
						cmd.inform('stat_cam%d="READY"' % (n + 1))
				if cmd:
					cmd.inform('inused_seq%d="NO"' % (seq_id + 1))
					cmd.finish()
			else:
				for n in cams:
					thread.start_new_thread(expose_call, (self.cams[n], expTime_ms, False))
				reactor.callLater(POLL_TIME, self.startsequence_bottom, cmd, seq_id, expTime_ms, \
				                  count, cams, cams, combined)

	def startsequence_abort(self, cmd, seq_id, cams, cams_check):
		""" Check if all cameras are ready after aborting """

		cams_busy = []
		for n in cams_check:
			if not self.cams[n].isReady():
				cams_busy.append(n)
			elif self.cams[n].tend > 0:
				if cmd:
					tread = self.cams[n].tend - self.cams[n].tstart
					cmd.diag('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
			else:
				if cmd:
					cmd.diag('text="AGC[%d]: Exposure aborted"' % (n + 1))
		if len(cams_busy) > 0:
			reactor.callLater(POLL_TIME, self.startsequence_abort, cmd, seq_id, cams, cams_busy)
		else:
			self.seq_stat[seq_id] = SEQ_IDLE
			for n in cams:
				self.cam_stat[n] = CAM_READY
				if cmd:
					cmd.inform('stat_cam%d="READY"' % (n + 1))
			if cmd:
				cmd.inform('inused_seq%d="NO"' % (seq_id + 1))
				cmd.inform('text="Sequence [%d] aborted"' % (seq_id + 1))
				cmd.finish()

	def stopsequence(self, cmd, seq_id):
		""" Stop a exposure sequence

		Args:
		   cmd      - a Command object to report to. Ignored if None.
		   seq_id   - Sequence ID
		"""

		if self.seq_stat[seq_id] != SEQ_RUNNING:
			if cmd:
				cmd.fail('text="Sequence ID %d not in used"' % (seq_id + 1))
			return
		self.seq_stat[seq_id] = SEQ_ABORT
		reactor.callLater(POLL_TIME, self.stopsequence_bottom, cmd, seq_id)

	def stopsequence_bottom(self, cmd, seq_id):
		""" Check if image sequence stopped

		Args:
		   cmd      - a Command object to report to. Ignored if None.
		   seq_id   - Sequence ID
		"""

		if self.seq_stat[seq_id] != SEQ_IDLE:
			reactor.callLater(POLL_TIME, self.stopsequence_bottom, cmd, seq_id)
		elif cmd:
			cmd.inform('text="Sequence [%d] aborted"' % (seq_id + 1))
			cmd.finish()

	def sequence_in_use(self, seq_id):
		""" Check if a sequence is in use """

		if self.seq_stat[seq_id] != SEQ_IDLE:
			return True
		else:
			return False

	def camera_stat(self, cam_id):
		""" Return the status of a camera """

		if self.cam_stat[cam_id] == CAM_NONEXISTENT:
			return "NONEXISTENT"
		elif self.cam_stat[cam_id] == CAM_BUSY:
			return "BUSY"
		else:
			return "READY"


def expose_call(cam, expTime_ms, dflag):
	""" Concurrent exposure thread for camera readouts """
	cam.setExpTime(expTime_ms)
	cam.expose(dark=dflag)

