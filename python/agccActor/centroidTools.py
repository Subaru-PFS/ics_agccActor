
from scipy.stats import sigmaclip
import yaml
import os
import numpy as np
import sep
from scipy.ndimage import gaussian_filter
from scipy.integrate import dblquad
from lmfit import Model
import lmfit
import dbRoutinesAGCC as dbTools


def getCentroidParams(cmd):

    try:
        cmdKeys=cmd.cmd.keywords
    except:
        cmdKeys=[]
        
    fileName=os.path.join(os.environ['ICS_AGCCACTOR_DIR'],'etc','agccDefaultCentroidParameters.yaml')

    with open(fileName, 'r') as inFile:
        defaultParms=yaml.load(inFile,Loader=yaml.Loader)
    #returns just the values dictionary
    centParms = defaultParms['values']

    if('nmin' in cmdKeys):
        centParms['nmin']=int(cmd.cmd.keywords["nmin"].values[0])
    if('thresh' in cmdKeys):
        centParms['thresh']=float(cmd.cmd.keywords["thresh"].values[0])
    if('deblend' in cmdKeys):
        centParms['deblend']=float(cmd.cmd.keywords["deblend"].values[0])

    return centParms


def updateTemplate(cmd,centParms):

    """
    load a pair of model PSF templates
    """

    
    #default value for unfocussed images
    dZ="+0.58"


    # we can choose a model from an explicitly given dZ
    if('dz' in cmdKeys):
        dZ=float(cmd.cmd.keywords["dz"].values[0])

        #get the dZ value for the closest model.
        #Negative and positive have different binning
        #if the value is larger/smaller than range, set to the edge,

        if(dZ > 0.98):
            dZString = "+0.98"
        elif(dZString < -0.9):
            dZString = "-0.90"
        elif(dZ > 0):
            dZString=f'{round(dZ/0.02)*0.02:+.2f}'
        else:
            dZString=f'{round(dZ/0.2)*0.2:+.2f}'

    
    fName=os.path.join(os.environ['PFS_INSTDATA_DIR'],'data','agc','psfTemplates',f'dZ{dZString}_SS0.70.fits')

    templateR = fits.getdata(fName)[0:81,:]
    templateL = fits.getdata(fName)[81:162,:]
    self.cParms['templateR'] = templateR
    self.cParms['templateL'] = templateL

    #larger gridsize for very unfocused images
    if(np.abs(dZ) > 0.4):
        self.cParms['gridSize']=31
    else:
        self.cParms['gridSize']=21

    return cParms,fName

def loadTemplate(focus,seeing):
    
    templatePath = "/Users/karr/Science/Templates/"
    fName = templatePath+"dZ"+focus+"_SS"+seeing+".fits"

    templateR = fits.getdata(fName)[0:81,:]
    templateL = fits.getdata(fName)[81:162,:]
    #templateR = np.flipud(fits.getdata(fName)[0:81,:])
    #templateL = np.flipud(fits.getdata(fName)[81:162,:])

    return templateL, templateR   

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

def getCentroidsTem(data,iParms,cParms,spotDtype,agcid):

    """
    runs centroiding for the sep routine and assigns the results
    """

    refFrame = cParms['refFrame']
    templateL = cParms['templateL']
    templateR = cParms['templateR']
    gridSize = cParms['gridSize']

    # get the reference positions for this camera ?? check 0/1 counting
    
    agNo = cParms['refpos'].values
    ind=np.where(agNo == agcid+1)
    xPos = cParms['refpos']['centroid_x_pix'].values[ind]
    yPos = cParms['refpos']['centroid_y_pix'].values[ind]
    
    # get region information for camera
    region = iParms[str(agcid + 1)]['reg']
    satValue = iParms['satVal']

    # keep the original value of the data for determining saturation later
    dataProc=subOverscan(data.astype('float'))
    dataProc=interpBadCol(dataProc,iParms[str(agcid + 1)]['badCols'])

    _data1 = dataProc[region[2]:region[3],region[0]:region[1]].astype('float', copy=True, order="C")
    _data2 = dataProc[region[6]:region[7],region[4]:region[5]].astype('float', copy=True, order="C")
    newData = dataProc.copy()
    newData[region[2]:region[3],region[0]:region[1]]-=background1
    newData[region[6]:region[7],region[4]:region[5]]-=background2


    nElem = len(xPos)
    result = np.zeros(nElem, dtype=spotDtype)

    #first, get the new positions (also flags for saturation and position, and background position)
    for k in range(len(xPos)):
        xP = xPos[k]
        yP = yPos[k]
        if(xP <= 536):
            newPos, pPos, pVal, sat = fitTemplate(templateL, newData, (xP,yP), gridSize)
            result['background'][k] = background1[pPos[1]-region[2], pPos[0]-region[0]]

            if(np.any([newPos[0]-2*fx < 0, newPos[1]+2*fx > (region[1]-region[0]),newPos[1]-2*fy < 0, newPos[1]+2*fy > (region[3]-region[2])],axis=0)):
                result['flags'][k] += 2


        else:
            newPos, pPos, pVal, sat = fitTemplate(templateR, newData, (xP,yP), gridSize)
            result['background'][k] = background2[pPos[1]-region[6], pPos[0]-region[4]]

            results['flags'][k]+=1
            if(np.any([newPos[0]-2*fx < 0, newPos[1]+2*fx > (region[5]-region[4]),newPos[1]-2*fy < 0, newPos[1]+2*fy > (region[7]-region[6])],axis=0)):
                result['flags'][k] += 2

        result['centroid_x_pix'][k]=newPos[0]
        result['centroid_y_pix'][k]=newPos[1]
        result['flags'][k] += sat
        result['peak_pixel_x_pix'][k]=pPos[0]
        result['peak_pixel_x_pix'][k]=pPos[1]
        result['peak_intensity'] = pPos

        # now the windowed second moments; need to think about what values when this doesn't converge??
        xv,yv, xyv, conv = windowedFWHM(newData, newPos[0], newPos[1])
        if(conv == 0):
            result['image_central_moment_02_pix'][k]=xv
            result['image_central_moment_20_pix'][k]=yv
            result['image_central_moment_11_pix'][k]=xyv
        else:
            result['image_central_moment_02_pix'][k]=0
            result['image_central_moment_20_pix'][k]=0
            result['image_central_moment_11_pix'][k]=0
        result['flags'][k] += conv
            
        # add flag for non converged sources
        flags.append(conv)

    #result['image_moment_00_pix'][nSpots1:nElem] = spots2['flux']
    return result

    
def getCentroidsSep(data,iParms,cParms,spotDtype,agcid):

    """
    runs centroiding for the sep routine and assigns the results
    """


    thresh=cParms['thresh']
    minarea=cParms['nmin']
    deblend=cParms['deblend']

    xPos, yPos = readSpotPos(db, frameId)
        

    # get region information for camera
    region = iParms[str(agcid + 1)]['reg']
    satValue = iParms['satVal']

    # keep the original value of the data for determining saturation later
    dataProc=subOverscan(data.astype('float'))
    dataProc=interpBadCol(dataProc,iParms[str(agcid + 1)]['badCols'])

    _data1 = dataProc[region[2]:region[3],region[0]:region[1]].astype('float', copy=True, order="C")
    _data2 = dataProc[region[6]:region[7],region[4]:region[5]].astype('float', copy=True, order="C")


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

    xx = x[:, 0]
    yy = x[:, 1]
    val=a*np.exp(-(xx-xC)**2 / (2*fX**2)-(yy-yC)**2 / (2*fY**2))+b
    return val
    
    
def fitTemplate(template, data, starPos, gridSize=21):
    
    """
    use cross correlation to fit a template to a spot of approximate known position
    
    input: 
        template: numpy array with template that matches the seeing and focus offset of the exposure
        data: input image
        starPos:  position of star from focussed image
        gridSize: size of grid to compute x-corr over
    
    output: 
        newPos: updated position
        sat: flag for saturated star

    note that the template is assumed to be square
    
    """

    # get the size of the template (assumes square)
    tSize = template.shape[0]
    
    # half point of template and grid
    g2 = gridSize // 2
    t2 = tSize // 2
   
    #integer values of star position
    xcI = int(np.round(starPos[0]))
    ycI = int(np.round(starPos[1]))

    # subimage centred on the star position
    dSub = data[ycI-g2:ycI+g2+1,xcI-g2:xcI+g2+1]
    
    # do the correlation
    # the built in python cross correlation routine turns out to
    # be pretty fast, as the underlying code is in C
    # mode = same gives us an output image the same size as the input
    
    sumVal=signal.correlate2d (dSub, template, mode='same')
            
    #find the offset of the max value from the centre of the grid
    offset = np.array(np.unravel_index(sumVal.argmax(),(gridSize,gridSize)))-g2

    #and the corresponding new position
    newPos = starPos - np.array([offset[1],offset[0]])
    
    # check for saturation
    if(dSub.max()==65535):
        sat=1
    else:
        sat=0

    #position and value of the peak position
    peakPix = np.unravel_index(dSub.argmax(),dSub.shape)+np.array([g2,g2])
    return newPos, peakPix, dSub.max(),sat
