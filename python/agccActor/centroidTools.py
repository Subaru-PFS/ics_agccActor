
from scipy.stats import sigmaclip
import yaml
import os
import numpy as np
import sep
from scipy.ndimage import gaussian_filter


def getCentroidParams(cmd):

    try:
        cmdKeys=cmd.cmd.keywords
    except:
        cmdKeys=[]
        
    fileName=os.path.join(os.environ['ICS_AGCCACTOR_DIR'],'etc','agccDefaultCentroidParameters.yaml')

    with open(fileName, 'r') as inFile:
        defaultParms=yaml.safe_load(inFile)
    
    #returns just the values dictionary
    centParms = defaultParms['values']

    if('nmin' in cmdKeys):
        centParms['nmin']=cmd.cmd.keywords["nmin"].values[0]
    if('thresh' in cmdKeys):
        centParms['thresh']=cmd.cmd.keywords["thresh"].values[0]

    return centParms

def getImageParams(cmd):

    try:
        cmdKeys=cmd.cmd.keywords
    except:
        cmdKeys=[]
        
    fileName=os.path.join(os.environ['ICS_AGCCACTOR_DIR'],'etc','agcCamParm.yaml')

    with open(fileName, 'r') as inFile:
        imageParms=yaml.safe_load(inFile)

    return imageParms

def interpBadCol(data,badCols):

    """
    interpolate over bad columns
    """

    for i in badCols:
        data[:,i]=(data[:,i-1]+data[:,i+1])/2
    return data


def subOverscan(data):

    """
    remove overscan
    """
    
    h, w = data.shape
    side0 = data[:, :w//2]
    side1 = data[:, w//2:]
    bg0 = np.median(side0[:, :4]).astype(data.dtype)
    bg1 = np.median(side1[:, -4:]).astype(data.dtype)

    data[:, :w//2] -= bg0
    data[:, w//2:] -= bg1

    return data

def centroidRegion(data, thresh, minarea=12):
    # determine the background
    bgClass = sep.Background(data)
    background = bgClass.back()
    rms = bgClass.rms()
    bgClass.subfrom(data)
    
    spots = sep.extract(data, thresh, rms, minarea = 12)

    return spots,len(spots),background

def getCentroidsSep(data,iParms,cParms,spotDtype,agcid):

    """
    runs centroiding for the sep routine and assigns the resules

    """

    thresh=cParms['thresh']
    minarea=cParms['nmin']

    # get region information for camera
    region = iParms[str(agcid + 1)]['reg']

    data=subOverscan(data.astype('float'))
    data=interpBadCol(data,iParms[str(agcid + 1)]['badCols'])
    
    _data1 = data[region[2]:region[3],region[0]:region[1]].astype('float', copy=True)
    _data2 = data[region[6]:region[7],region[4]:region[5]].astype('float', copy=True)

    spots1, nSpots1, background1 = centroidRegion(_data1, thresh, minarea)
    spots2, nSpots2, background2 = centroidRegion(_data2, thresh, minarea)

    nElem = nSpots1 + nSpots2

    result = np.zeros(nElem, dtype=spotDtype)
    

    result['image_moment_00_pix'][0:nSpots1] = spots1['flux']
    result['centroid_x_pix'][0:nSpots1] = spots1['x']+region[0]
    result['centroid_y_pix'][0:nSpots1] = spots1['y']+region[2]
    result['central_image_moment_20_pix'][0:nSpots1] = spots1['x2']
    result['central_image_moment_11_pix'][0:nSpots1] = spots1['xy']
    result['central_image_moment_02_pix'][0:nSpots1] = spots1['y2']
    result['peak_pixel_x_pix'][0:nSpots1] = spots1['xpeak']+region[0]
    result['peak_pixel_y_pix'][0:nSpots1] = spots1['ypeak']+region[2]
    result['peak_intensity'][0:nSpots1] = spots1['peak']
    result['background'][0:nSpots1] = background1[spots1['ypeak'], spots1['xpeak']]
    
    result['image_moment_00_pix'][nSpots1:nElem] = spots2['flux']
    result['centroid_x_pix'][nSpots1:nElem] = spots2['x']+region[4]
    result['centroid_y_pix'][nSpots1:nElem] = spots2['y']+region[6]
    result['central_image_moment_20_pix'][nSpots1:nElem] = spots2['x2']
    result['central_image_moment_11_pix'][nSpots1:nElem] = spots2['xy']
    result['central_image_moment_02_pix'][nSpots1:nElem] = spots2['y2']
    result['peak_pixel_x_pix'][nSpots1:nElem] = spots2['xpeak']+region[4]
    result['peak_pixel_y_pix'][nSpots1:nElem] = spots2['ypeak']+region[6]
    result['peak_intensity'][nSpots1:nElem] = spots2['peak']
    result['background'][nSpots1:nElem] = background2[spots2['ypeak'], spots2['xpeak']]
    # set flag for right half of image
    result['flag'][0:nSpots1] += 1

    return result


    
