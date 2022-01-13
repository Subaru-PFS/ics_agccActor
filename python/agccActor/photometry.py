import numpy as np
import centroidTools as ct
from importlib import reload
import multiprocessing as mp
import sep
import logging

spotDtype = np.dtype(dict(names=['image_moment_00_pix', 'centroid_x_pix', 'centroid_y_pix', 'central_image_moment_20_pix', 'central_image_moment_11_pix', 'central_image_moment_02_pix', 'peak_pixel_x_pix', 'peak_pixel_y_pix', 'peak_intensity', 'background', 'flags'],
                          formats=['f4', 'f4', 'f4', 'f4', 'f4' ,'f4', 'i2', 'i2', 'f4', 'f4', 'i2']))


logger = logging.getLogger('photometry')
logger.setLevel(logging.DEBUG)

def removeOverscan(im):
    h, w = im.shape
    side0 = im[:, :w//2]
    side1 = im[:, w//2:]
    bg0 = np.median(side0[:, :4]).astype(im.dtype)
    bg1 = np.median(side1[:, -4:]).astype(im.dtype)

    im[:, :w//2] -= bg0
    im[:, w//2:] -= bg1

    return im, bg0, bg1

def removeBackground(im):
    h, w = im.shape
    side0 = im[:, :w//2]
    side1 = im[:, w//2:]
    bg0 = np.median(side0).astype(im.dtype)
    bg1 = np.median(side1).astype(im.dtype)

    im[:, :w//2] -= bg0
    im[:, w//2:] -= bg1

    return im, (bg0 + bg1)/2

def measure(data,cParms,cMethod,thresh=15):
    """ measure centroid positions """
    _data = data.astype('float', copy=True)
    try:
        data, bg0, bg1 = removeOverscan(_data)
    except Exception as e:
        logger.warn(f'boom: {e}')

        
    if(cMethod == 'sep'):
        result = ct.getCentroidSep(image,iParms,spotDtype,agcid):
        
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
            
            result = measure(data,cParms,cMethod)
            out_q.put(result)

    in_q = mp.Queue()
    out_q = mp.Queue()
    p = mp.Process(target=worker, args=(in_q, out_q), daemon=True)
    p.start()
    return in_q, out_q
