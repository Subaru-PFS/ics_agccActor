import numpy as np
import sep
import multiprocessing as mp

spotDtype = np.dtype(dict(names=['m00', 'm10', 'm01', 'm20', 'm11', 'm02', 'xpeak', 'ypeak', 'peak', 'bg'],
                          formats=['f4', 'f4', 'f4', 'f4', 'f4' ,'f4', 'i2', 'i2', 'f4', 'f4']))

def measure(data, thresh=10):
    """ measure centroid positions """
    _data = data.astype('float', copy=True)
    bgClass = sep.Background(_data)
    background = bgClass.back()
    rms = bgClass.rms()
    bgClass.subfrom(_data)

    spots = sep.extract(_data, thresh, rms)
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
    result['bg'] = background[spots['xpeak'], spots['ypeak']]

    return result

def createProc(thresh=10):
    """ multiprocessing for photometry """
    def worker(in_q, out_q, thresh=10):
        while (True):
            data = in_q.get()
            result = measure(data, thresh)
            out_q.put(result)

    in_q = mp.Queue()
    out_q = mp.Queue()
    p = mp.Process(target=worker, args=(in_q, out_q, thresh), daemon=True)
    p.start()
    return in_q, out_q
