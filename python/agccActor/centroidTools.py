
from scipy.stats import sigmaclip
import yaml
import os
import numpy as np
import sep
from scipy.ndimage import gaussian_filter

from scipy.integrate import dblquad
from lmfit import Model
import lmfit

from lmfit import Model
import lmfit


def getCentroidParams(cmd):

    """
    read in the centroiding parameters from config file
    """

    try:
        cmdKeys=cmd.cmd.keywords
    except:
        cmdKeys=[]
        
    fileName=os.path.join(os.environ['PFS_INSTDATA_DIR'],'config/actors','agcc.yaml')

    with open(fileName, 'r') as inFile:
        defaultParms=yaml.safe_load(inFile)
    
    #returns just the values dictionary
    centParms = defaultParms['agcc']['centroidParams']

    if('nmin' in cmdKeys):
        centParms['nmin']=int(cmd.cmd.keywords["nmin"].values[0])
    if('thresh' in cmdKeys):
        centParms['thresh']=float(cmd.cmd.keywords["thresh"].values[0])
    if('deblend' in cmdKeys):
        centParms['deblend']=float(cmd.cmd.keywords["deblend"].values[0])

    return centParms

def getImageParams(cmd):

    """
    read in instrumental parameters from config file
    """

    try:
        cmdKeys=cmd.cmd.keywords
    except:
        cmdKeys=[]
        
    fileName=os.path.join(os.environ['PFS_INSTDATA_DIR'],'config/actors','agcc.yaml')

    with open(fileName, 'r') as inFile:
        imageParms=yaml.safe_load(inFile)

    return imageParms['agcc']['cameraParams']

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

    """
    wrapper that subtract the background and calls the centroiding
    """
    
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

    dataProc=subOverscan(data.astype('float'))
    dataProc=interpBadCol(dataProc,iParms[str(agcid + 1)]['badCols'])
    
    _data1 = dataProc[region[2]:region[3],region[0]:region[1]].astype('float', copy=True, order="C")
    _data2 = dataProc[region[6]:region[7],region[4]:region[5]].astype('float', copy=True, order="C")

    spots1, nSpots1, background1  = centroidRegion(_data1, thresh, minarea,deblend=deblend)
    spots2, nSpots2, background2  = centroidRegion(_data2, thresh, minarea,deblend=deblend)

    nElem = nSpots1 + nSpots2

    result = np.zeros(nElem, dtype=spotDtype)

    # flag spots near edge of region

    # dynamic fwhm calculation is overenthusiastic with out of focus images
    #fx = spots1['x2'].mean()
    #fy = spots1['y2'].mean()

    fx = 5
    fy = 5
    
    ind1 = np.where(np.any([spots1['x']-2*fx < 0, spots1['x']+2*fx > (region[1]-region[0]),spots1['y']-2*fy < 0, spots1['y']+2*fy > (region[3]-region[2])],axis=0))
    #ind2 = spots1['peak'] == satValue
    

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
    #result['flags'][0:nSpots1][ind2] += 4

    # flag spots near edge of region


    #fx = spots2['x2'].mean()
    #fy = spots2['y2'].mean()
    fx = 5
    fy = 5

    ind1 = np.where(np.any([spots2['x']-2*fx < 0, spots2['x']+2*fx > (region[5]-region[4]),spots2['y']-2*fy < 0, spots2['y']+2*fy > (region[7]-region[6])],axis=0))
    #ind2 = spots2['peak'] == satValue
    
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
    #result['flags'][nSpots1:nElem][ind2] += 4

    # determine saturation off the unprocessed data
    satFlag = data[result['peak_pixel_y_pix'],result['peak_pixel_x_pix']]==satValue
    result['flags'] += satFlag*4
    
    # calculate more reasonable FWHMs

    # subract the background

    newData = dataProc.copy()
    newData[region[2]:region[3],region[0]:region[1]]-=background1
    newData[region[6]:region[7],region[4]:region[5]]-=background2
    
    m20 = []
    m02 = []
    m11 = []

    flags = []
    for ii in range(len(result)):
    
        yPos=result['centroid_x_pix'][ii]
        xPos=result['centroid_y_pix'][ii]
    
        xv,yv, xyv, conv = windowedFWHM(newData, yPos, xPos)
        #xv, yv = fittedFWHM(newData, yPos, xPos)

        # if the moment didn't converge, revert to the unweighted second moment and set flags
        if(conv == 0):
            m02.append(xv)
            m20.append(yv)
            m11.append(xyv)
        else:
            m02.append(result['central_image_moment_20_pix'][ii])
            m20.append(result['central_image_moment_02_pix'][ii])
            m11.append(result['central_image_moment_11_pix'][ii])
            
            
        # add flag for non converged sources
        flags.append(conv)

        
    # and update the values
    result['central_image_moment_20_pix']=np.array(m20)
    result['central_image_moment_02_pix']=np.array(m02)
    result['central_image_moment_11_pix']=np.array(m11)
    result['flags'] = result['flags']+np.array(flags)
    result['estimated_magnitude'] = calculateApproximateMagnitude(iParms,result['image_moment_00_pix'],cParms['expTime'])

    return result

def windowedFWHM(data,xPos,yPos):

    """
    windowed second moments, based on pre-determined positions
    """
    
    maxIt = 30
    boxSize=20

    # determine the sub-image region
    dMinX = int(xPos - boxSize)
    dMaxX = int(xPos + boxSize + 1)
    dMinY = int(yPos - boxSize)
    dMaxY = int(yPos + boxSize + 1)

    # check for edges of image
    dMinX = np.max([dMinX,0])
    dMinY = np.max([dMinY,0])
    dMaxX = np.min([dMaxX,data.shape[1]])
    dMaxY = np.min([dMaxY,data.shape[0]])


    # and the sub-image
    winVal = data[dMinY:dMaxY,dMinX:dMaxX]

    # scale the coordinates by the central position, to avoid numeric overflow

    xVal = np.arange(dMinX,dMaxX)-(dMaxX+dMinX)/2
    yVal = np.arange(dMinY,dMaxY)-(dMaxY+dMinY)/2
    xv,yv = np.meshgrid(xVal,yVal)


    
    # initial values
    sx = 1.5
    sy = 1.5
    sxy = 0

    w11 = -1
    w12 = -1
    w22 = -1

    # some variables for iteration
    e1_old=1e6
    e2_old=1e6
    sx_o=1e6
    tol1=0.001
    tol2=0.01

    # now the iteration
    for i in range(0,maxIt):

        # get the weighting function based on the current values
        # of the moments

        ow11 = w11
        ow12 = w12
        ow22 = w22

        detw = sx*sy-sxy**2
        w11 = sy/detw
        w12 = -sxy/detw
        w22 = sx/detw

        r2 = xv*xv*w11 + yv*yv*w22 + 2*w12*xv*yv
        w = np.exp(-r2/2)
        #print(f'{r2.min():.2f},{r2.max():.2f},{w.min():.2f},{w.max():.2f}')

        # and calcualte the weighted moments
        sxow = (winVal * w * (xv)**2).sum()/(winVal * w).sum()
        syow = (winVal * w * (yv)**2).sum()/(winVal * w).sum()
        sxyow = (winVal * w * xv*yv).sum()/(winVal * w).sum()
        # variables to test for convergence
        d = sxow + syow
        e1 = (sxow - syow)/d
        e2 = 2*sxyow/d
        

        # check for convergence
        if(np.all([np.abs(e1-e1_old) < tol1, np.abs(e2-e2_old) < tol1, np.abs(sx/sx_o - 1) < tol2])):
            return sxow, syow, sxyow, 0

        # calculate new values 
        e1_old=e1
        e2_old=e2
        sx_o = sx

        detow = sxow*syow-sxy**2
        ow11 = syow/detow
        ow12 = -sxyow/detow
        ow22 = sxow/detow

        n11 = ow11 - w11
        n12 = ow12 - w12
        n22 = ow22 - w22
        det_n = n11*n22 - n12*n12
        
        sx = n22/det_n
        sxy = -n12/det_n
        sy = n11/det_n

    # if we haven't converged return new values
    return sx,sy,sxy, 8

def fittedFWHM(data, xPos, yPos):

    """
    fit gaussian to pre-calculated centre
    """

    ww = 10

    # x and y position grid
    sz = data.shape
    x=np.arange(0,sz[0])
    y=np.arange(0,sz[1])
    xx, yy = np.meshgrid(y,x)

    #determine subImage
    miX=int(xPos-ww)
    maX=int(xPos+ww+1)
    miY=int(yPos-ww)
    maY=int(yPos+ww+1)
        
    subX=xx[miX:maX,miY:maY]
    subY=yy[miX:maX,miY:maY]
    subD = data[miX:maX,miY:maY]
        
    sz=subX.shape
        
    dd = np.empty((sz[0]*sz[1],3))
    dd[:,0]=subX.flatten()
    dd[:,1]=subY.flatten()
    dd[:,2]=subD.flatten()
        
    gmod = Model(gaussian)
    gmod.set_param_hint('xC', value=yPos)
    gmod.set_param_hint('yC', value=xPos)
    gmod.set_param_hint('fX', value=2,min=0,max=10)
    gmod.set_param_hint('fY', value=2,min=0,max=10)
    gmod.set_param_hint('a', value=1000,min=0,max=subD.max()*1.5)
    gmod.set_param_hint('b', value=subD.min())
        
    params = gmod.make_params()
    params['xC'].set(vary=False)
    params['yC'].set(vary=False)
        
    fitResult = gmod.fit(dd[:, 2], x=dd[:, 0:2], params=params)

    return fitResult.best_values['fX'], fitResult.best_values['fY']


def gaussian(x, xC, yC, fX, fY, a, b):

    """
    2D gaussian functino for fit s
    """

    xx = x[:, 0]
    yy = x[:, 1]
    val=a*np.exp(-(xx-xC)**2 / (2*fX**2)-(yy-yC)**2 / (2*fY**2))+b
    return val
  

def calculateApproximateMagnitude(iParms,instrumentFlux,expTime):

    """
    empirical function for gaia magnitudes
    """

    mag = -2.5*np.log10(instrumentFlux/expTime)*iParms['magFit'][0]+iParms['magFit'][1]

    return mag
