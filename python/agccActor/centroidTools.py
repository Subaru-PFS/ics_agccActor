
from scipy.stats import sigmaclip
import yaml
import os
import numpy as np
import sep
from scipy.ndimage import gaussian_filter


def getImageParams(cmd):

    try:
        cmdKeys=cmd.cmd.keywords
    except:
        cmdKeys=[]
        
    fileName=os.path.join(os.environ['ICS_AGCCACTOR_DIR'],'etc','agCamParameters.yaml')

    with open(fileName, 'r') as inFile:
        imageParms=yaml.safe_load(inFile)

    return imageParms

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

    if('fwhmx' in cmdKeys):
        centParms['fwhmx']=cmd.cmd.keywords["fwhmx"].values[0]
    if('fwhmy' in cmdKeys):
        centParms['fwhmy']=cmd.cmd.keywords["fwhmy"].values[0]

    if('boxFind' in cmdKeys):
        centParms['boxFind']=cmd.cmd.keywords["boxFind"].values[0]
    if('boxCent' in cmdKeys):
        centParms['boxCent']=cmd.cmd.keywords["boxCent"].values[0]

    if('findSigma' in cmdKeys):
        centParms['findSigma']=cmd.cmd.keywords["findSigma"].values[0]
    if('centSigma' in cmdKeys):
        centParms['centSigma']=cmd.cmd.keywords["centSigma"].values[0]
    if('threshSigma' in cmdKeys):
        centParms['threshSigma']=cmd.cmd.keywords["threshSigma"].values[0]

    if('nmin' in cmdKeys):
        centParms['nmin']=cmd.cmd.keywords["nmin"].values[0]
    if('nmax' in cmdKeys):
        centParms['nmax']=cmd.cmd.keywords["nmax"].values[0]
    if('nmax' in cmdKeys):
        centParms['maxIt']=cmd.cmd.keywords["maxIt"].values[0]


    return centParms


def interpBadCol(data,badCols):

    w,h = data.shape()
    for i in badCols:
        for j in range(h):
            data[i,j]=(data[i-1,j]+data[i+1],j)/2
    return data

    
def getCentroidsSep(data,iParms,spotDtype,agcid,thresh):

    """
    runs centroiding for the sep routine and assigns the resules

    """

    # this is needed for sep
    from scipy.ndimage import gaussian_filter
    
    region = iParms[str(int(agcid))]['reg']

    data=interpBadCol(data,iParms[str(int(agcid))]['badcols'])
    
    _data1 = data[region[2]:region[3],region[0]:region[1]].astype('float', copy=True)
    _data2 = data[region[6]:region[7],region[4]:region[5]].astype('float', copy=True)

    # determine the background
    bgClass1 = sep.Background(_data1)
    background1 = bgClass1.back()
    rms1 = bgClass1.rms()
    bgClass1.subfrom(_data1)

    spots1 = sep.extract(_data1, thresh, rms1, minarea = 10)

    # determine the background
    bgClass2 = sep.Background(_data2)
    background2 = bgClass2.back()
    rms2 = bgClass2.rms()
    bgClass2.subfrom(_data2)

    spots2 = sep.extract(_data2, thresh, rms2, minarea = 10)

    nElem = len(spots1)+len(spots2)

    result = np.zeros(nElem, dtype=spotDtype)
    print(spots1['npix'])

    result['image_moment_00_pix'][0:len(spots1)] = spots1['flux']
    result['centroid_x_pix'][0:len(spots1)] = spots1['x']+region[0]
    result['centroid_y_pix'][0:len(spots1)] = spots1['y']+region[2]
    result['central_image_moment_20_pix'][0:len(spots1)] = spots1['x2']
    result['central_image_moment_11_pix'][0:len(spots1)] = spots1['xy']
    result['central_image_moment_02_pix'][0:len(spots1)] = spots1['y2']
    result['peak_pixel_x_pix'][0:len(spots1)] = spots1['xpeak']+region[0]
    result['peak_pixel_y_pix'][0:len(spots1)] = spots1['ypeak']+region[2]
    result['peak_intensity'][0:len(spots1)] = spots1['peak']
    result['background'][0:len(spots1)] = background1[spots1['ypeak'], spots1['xpeak']]
    
    result['image_moment_00_pix'][len(spots1):nElem] = spots2['flux']
    result['centroid_x_pix'][len(spots1):nElem] = spots2['x']+region[4]
    result['centroid_y_pix'][len(spots1):nElem] = spots2['y']+region[6]
    result['central_image_moment_20_pix'][len(spots1):nElem] = spots2['x2']
    result['central_image_moment_11_pix'][len(spots1):nElem] = spots2['xy']
    result['central_image_moment_02_pix'][len(spots1):nElem] = spots2['y2']
    result['peak_pixel_x_pix'][len(spots1):nElem] = spots2['xpeak']+region[4]
    result['peak_pixel_y_pix'][len(spots1):nElem] = spots2['ypeak']+region[6]
    result['peak_intensity'][len(spots1):nElem] = spots2['peak']
    result['background'][len(spots1):nElem] = background2[spots2['ypeak'], spots2['xpeak']]
    # set flag for right half of image
    result['flag'][0:len(spots1)] += 1

    


    
