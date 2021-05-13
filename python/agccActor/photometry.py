import numpy as np
import sep

spotDtype = np.dtype(dict(names=['m00', 'm10', 'm01', 'm20', 'm11', 'm02', 'xpeak', 'ypeak', 'peak', 'bg'],
	                      formats=['f4', 'f4', 'f4', 'f4', 'f4' ,'f4', 'i2', 'i2', 'f4', 'f4']))

def measure(data, thresh=10):
	""" measure centroid positions """

	data = data.astype('float')
	bgClass = sep.Background(data)
	background = bgClass.back()
	rms = bgClass.rms()
	bgClass.subfrom(data)

	spots = sep.extract(data, thresh, rms)
	result = np.zeros(len(spots), dtype=spotDtype)

	# need to ckeck if the following definition are correct
	result['m00'] = spots['flux']
	result['m10'] = spots['x']
	result['m01'] = spots['y']
	result['m20'] = spots['x2']
	result['m11'] = spots['xy']
	result['m02'] = spots['y2']
	result['xpeak'] = spots['xpeak']
	result['ypeak'] = spots['ypeak']
	result['peak'] = spots['peak']
	for n in range(len(spots)):
		result[n]['bg'] = background[spots['xpeak'], spots['ypeak']]

	return result
