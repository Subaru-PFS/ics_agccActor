import numpy as np
import centroidTools as ct
from importlib import reload
import multiprocessing as mp
import sep
import logging

spotDtype = np.dtype(dict(names=['image_moment_00_pix', 'centroid_x_pix', 'centroid_y_pix', 'central_image_moment_20_pix', 'central_image_moment_11_pix', 'central_image_moment_02_pix', 'peak_pixel_x_pix', 'peak_pixel_y_pix', 'peak_intensity', 'background'],
                          formats=['f4', 'f4', 'f4', 'f4', 'f4' ,'f4', 'i2', 'i2', 'f4', 'f4']))

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

def measure(data,cParms,cMethod,thresh=10):
    """ measure centroid positions """
    _data = data.astype('float', copy=True)
    try:
        data, bg0, bg1 = removeOverscan(_data)
    except Exception as e:
        logger.warn(f'boom: {e}')


    if(cMethod == 'win'): 
        spots = ct.getCentroids(_data,cParms)
        result = np.zeros(len(spots), dtype=spotDtype)
        # need to ckeck if the following definition are correct
        result['image_moment_00_pix'] = spots[:,9]
        result['centroid_x_pix'] = spots[:,1]
        result['centroid_y_pix'] = spots[:,2]
        result['central_image_moment_20_pix'] = spots[:,5]
        result['central_image_moment_11_pix'] = spots[:,7]
        result['central_image_moment_02_pix'] = spots[:,6]
        result['peak_pixel_x_pix'] = spots[:,3]
        result['peak_pixel_y_pix'] = spots[:,4]
        result['peak_intensity'] = spots[:,8]
        result['background'] = spots[:,10]
        
    if(cMethod == 'sep'):

        bgClass = sep.Background(_data)
        background = bgClass.back()
        rms = bgClass.rms()
        bgClass.subfrom(_data)

        spots = sep.extract(_data, thresh, rms)
        result = np.zeros(len(spots), dtype=spotDtype)

        result['image_moment_00_pix'] = spots['flux']
        result['centroid_x_pix'] = spots['x']
        result['centroid_y_pix'] = spots['y']
        result['central_image_moment_20_pix'] = spots['x2']
        result['central_image_moment_11_pix'] = spots['xy']
        result['central_image_moment_02_pix'] = spots['y2']
        result['peak_pixel_x_pix'] = spots['xpeak']
        result['peak_pixel_y_pix'] = spots['ypeak']
        result['peak_intensity'] = spots['peak']
        result['background'] = background[spots['xpeak'], spots['ypeak']]

    return result

def createProc():
    """ multiprocessing for photometry """
    def worker(in_q, out_q):
        while (True):
            data = in_q.get()
            cParms = in_q.get()
            cMethod = in_q.get()
            
            result = measure(data,cParms,cMethod)
            out_q.put(result)

    in_q = mp.Queue()
    out_q = mp.Queue()
    p = mp.Process(target=worker, args=(in_q, out_q), daemon=True)
    p.start()
    return in_q, out_q
