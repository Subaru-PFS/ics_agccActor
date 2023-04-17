import numpy as np
import centroidTools as ct
from importlib import reload
import multiprocessing as mp
import sep
import logging

spotDtype = np.dtype(dict(names=['image_moment_00_pix', 'centroid_x_pix', 'centroid_y_pix', 'central_image_moment_20_pix', 'central_image_moment_11_pix', 'central_image_moment_02_pix', 'peak_pixel_x_pix', 'peak_pixel_y_pix', 'peak_intensity', 'background', 'estimated_magnitude', 'flags'],
                          formats=['f4', 'f4', 'f4', 'f4', 'f4' ,'f4', 'i2', 'i2', 'f4', 'f4', 'f4', 'i2']))


def measure(data,agcid,cParms,iParms,cMethod,thresh=10):

    """ measure centroid positions """
        
    if(cMethod == 'sep'):

        result = ct.getCentroidsSep(data,iParms,cParms,spotDtype,agcid)
        
    return result

def createProc():
    """ multiprocessing for photometry """
    def worker(in_q, out_q):
        while (True):
            data = in_q.get()
            agcid = in_q.get()
            cParms = in_q.get()
            iParms = in_q.get()
            cMethod = in_q.get()
            
            result = measure(data,agcid,cParms,iParms,cMethod)

            out_q.put(result)

    in_q = mp.Queue()
    out_q = mp.Queue()
    p = mp.Process(target=worker, args=(in_q, out_q), daemon=True)
    p.start()
    return in_q, out_q
