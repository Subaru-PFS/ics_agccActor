import numpy as np
import centroidTools as ct
from importlib import reload
import multiprocessing as mp

spotDtype = np.dtype(dict(names=['m00', 'm10', 'm01', 'm20', 'm11', 'm02', 'xpeak', 'ypeak', 'peak', 'bg'],
                          formats=['f4', 'f4', 'f4', 'f4', 'f4' ,'f4', 'i2', 'i2', 'f4', 'f4']))

def measure(data,cParms):
    """ measure centroid positions """
    _data = data.astype('float', copy=True)
 
    reload(ct)
    spots = ct.getCentroids(_data,cParms)
    result = np.zeros(len(spots), dtype=spotDtype)

    # need to ckeck if the following definition are correct
    result['m00'] = spots[:,9]
    result['m10'] = spots[:,1]
    result['m01'] = spots[:,2]
    result['m20'] = spots[:,5]
    result['m11'] = spots[:,7]
    result['m02'] = spots[:,6]
    result['xpeak'] = spots[:,3]
    result['ypeak'] = spots[:,4]
    result['peak'] = spots[:,8]
    result['bg'] = spots[:,10]

    return result,spots

def createProc():
    """ multiprocessing for photometry """
    def worker(in_q, out_q):
        while (True):
            data = in_q.get()
            cParms = in_q.get()
            result, centroids = measure(data,cParms)
            out_q.put(result)
            out_q.put(centroids)

    in_q = mp.Queue()
    out_q = mp.Queue()
    p = mp.Process(target=worker, args=(in_q, out_q), daemon=True)
    p.start()
    return in_q, out_q
