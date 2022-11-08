
from scipy.stats import sigmaclip
import yaml
import os
import numpy as np
import sep
from scipy.ndimage import gaussian_filter

from scipy.integrate import dblquad

from lmfit import Model


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
        centParms['nmin']=int(cmd.cmd.keywords["nmin"].values[0])
    if('thresh' in cmdKeys):
        centParms['thresh']=float(cmd.cmd.keywords["thresh"].values[0])
    if('deblend' in cmdKeys):
        centParms['deblend']=float(cmd.cmd.keywords["deblend"].values[0])

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

def centroidRegion(data, thresh, minarea=12, deblend = 0.5):
    
    # determine the background
    bgClass = sep.Background(data)
    background = bgClass.back()
    rms = bgClass.rms()
    bgClass.subfrom(data)
    
    spots = sep.extract(data, thresh, rms, minarea = minarea, deblend_cont=deblend)

    return spots,len(spots),background

def getCentroidsSep(data,iParms,cParms,spotDtype,agcid):

    """
    runs centroiding for the sep routine and assigns the results
    """


    thresh=cParms['thresh']
    minarea=cParms['nmin']
    deblend=cParms['deblend']

    # get region information for camera
    region = iParms[str(agcid + 1)]['reg']
    satValue = iParms['satVal']
    
    data=subOverscan(data.astype('float'))
    data=interpBadCol(data,iParms[str(agcid + 1)]['badCols'])


    spots1, nSpots1, background1 = centroidRegion(_data1, thresh, minarea=minarea, deblend=deblend)
    spots2, nSpots2, background2 = centroidRegion(_data2, thresh, minarea=minarea, deblend=deblend)

    newData = data.astype('float', copy=True)
    
    _data1 = data[region[2]:region[3],region[0]:region[1]]
    _data2 = data[region[6]:region[7],region[4]:region[5]]

    spots1, nSpots1, background1  = centroidRegion(_data1, thresh, minareadeblend=deblend)
    spots2, nSpots2, background2  = centroidRegion(_data2, thresh, minareadeblend=deblend)


    nElem = nSpots1 + nSpots2

    result = np.zeros(nElem, dtype=spotDtype)

    # flag spots near edge of region

    # dynamic fwhm calculation is overenthusiastic with out of focus images
    #fx = spots1['x2'].mean()
    #fy = spots1['y2'].mean()

    fx = 5
    fy = 5
    
    ind1 = np.where(np.any([spots1['x']-2*fx < 0, spots1['x']+2*fx > (region[1]-region[0]),spots1['y']-2*fy < 0, spots1['y']+2*fy > (region[3]-region[2])],axis=0))
    ind2 = spots1['peak'] == satValue
    

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
    result['flags'][0:nSpots1][ind1] += 2
    result['flags'][0:nSpots1][ind2] += 4

    # flag spots near edge of region

    #fx = spots2['x2'].mean()
    #fy = spots2['y2'].mean()
    fx = 5
    fy = 5

    ind1 = np.where(np.any([spots2['x']-2*fx < 0, spots2['x']+2*fx > (region[5]-region[4]),spots2['y']-2*fy < 0, spots2['y']+2*fy > (region[7]-region[6])],axis=0))
    ind2 = spots2['peak'] == satValue
    
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
    result['flags'][nSpots1:nElem] += 1

    result['flags'][nSpots1:nElem][ind1] += 2
    result['flags'][nSpots1:nElem][ind2] += 4

    # calculate more reasonable FWHMs

    # subract the background
    
    newData[region[2]:region[3],region[0]:region[1]]-=background1
    newData[region[6]:region[7],region[4]:region[5]]-=background2
    
    # x and y position grid
    sz = data.shape
    x=np.arange(0,sz[0])
    y=np.arange(0,sz[1])
    xx, yy = numpy.meshgrid(x, y)

    # define the model
    gmod = Model(gaussian)
    gmod.set_param_hint('fX', value=2,min=0,max=10)
    gmod.set_param_hint('fY', value=2,min=0,max=10)
    gmod.set_param_hint('a', value=1000,min=0,max=1e6)
    gmod.set_param_hint('b', value=0,min=0,max=100)

    # keep track of the updated values
    m20 = []
    m02 = []

    #cycle over the results
    for i in range(0,len(results)):

        # define a subregion aroudn the centroid
        xv = result['centroid_x_pix'][i]
        yv = result['centroid_y_pix'][i]

        minX = xv-ww
        maxX = xv+ww+1
        minU = yv-ww
        maxY = yv+ww+1
        
        subX=xx[minX:mxaX,mivY:maxY]
        subY=yy[minX:mxaX,mivY:maxY]
        subD = sData[minX:maxX,minY:maxY]

        # massage into a form that the fitting function likes
        sz=subX.shape        
        dd = numpy.empty((sz[0]*sz[1],3))
        dd[:,0]=subX.flatten()
        dd[:,1]=subY.flatten()
        dd[:,2]=subD.flatten()

        # set the x and y starting values, and define them as fixed
        
        gmod.set_param_hint('xC', value=xv)
        gmod.set_param_hint('yC', value=yv)

        # make the parameter object
        params = gmod.make_params()

        # fix the positions, because we know them already

        params['xC'].set(vary=False)
        params['yC'].set(vary=False)

        # do the fit
        result = gmod.fit(dd[:, 2], x=dd[:, 0:2], params=params)

        m02.append(result.best_values['fX'])
        m20.append(result.best_values['fY'])

    # and update the values
    result['central_image_moment_20_pix']=20
    result['central_image_moment_02_pix']=02
     
    return result



def gaussian(coord, xC, yC, fX, fY, a, b):

    x = coord[:, 0]
    y = coord[:, 1]
    val=a*numpy.exp(-(x-xC)**2 / (2*fX**2)-(y-yC)**2 / (2*fY**2))+b
    return val
  

