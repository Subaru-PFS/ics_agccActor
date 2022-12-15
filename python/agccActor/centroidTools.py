
from scipy.stats import sigmaclip
import yaml
import os
import numpy as np
import sep
from scipy.ndimage import gaussian_filter
from scipy.integrate import dblquad
from lmfit import Model
import lmfit
from agccActor import dbRoutinesAGCC as dbTools
from scipy import signal
from scipy.optimize import curve_fit
from astropy.io import fits

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

    try:
        cmdKeys=cmd.cmd.keywords
    except:
        cmdKeys=[]

    #default value for unfocussed images
    dZ=0.58


    # we can choose a model from an explicitly given dZ
    if('dz' in cmdKeys):
        dZ=float(cmd.cmd.keywords["dz"].values[0])

    #get the dZ value for the closest model.
    #Negative and positive have different binning
    #if the value is larger/smaller than range, set to the edge,

    print(dZ)
    if(dZ > 0.98):
        dZString = "+0.98"
    elif(dZ < -0.9):
        dZString = "-0.90"
    elif(dZ > 0):
        dZString=f'{round(dZ/0.02)*0.02:+.2f}'
    else:
        dZString=f'{round(dZ/0.2)*0.2:+.2f}'

    
    fName=os.path.join(os.environ['PFS_INSTDATA_DIR'],'data','agc','psfTemplates',f'dZ{dZString}_SS0.70.fits')

    templateR = fits.getdata(fName)[0:81,:]
    templateL = fits.getdata(fName)[81:162,:]
    centParms['templateR'] = templateR
    centParms['templateL'] = templateL
    centParms['dZ'] = dZ
    
    #larger gridsize for very unfocused images
    if(np.abs(dZ) > 0.4):
        centParms['gridSize']=31
    else:
        centParms['gridSize']=21

    return centParms,fName

def loadTemplate(focus,seeing):
    
    templatePath = "/Users/karr/Science/Templates/"
    fName = templatePath+"dZ"+focus+"_SS"+seeing+".fits"

    templateR = fits.getdata(fName)[0:81,:]
    templateL = fits.getdata(fName)[81:162,:]

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

    templateL = cParms['templateL']
    templateR = cParms['templateR']
    gridSize = cParms['gridSize']

    # get the reference positions for this camera ?? check 0/1 counting
    
    #agNo = cParms['refpos']
    #ind=np.where(agNo == agcid+1)
    xPos = cParms['refpos']['centroid_x_pix']
    yPos = cParms['refpos']['centroid_y_pix']
    
    # get region information for camera
    region = iParms[str(agcid + 1)]['reg']
    satValue = iParms['satVal']

    # keep the original value of the data for determining saturation later
    dataProc=subOverscan(data.astype('float'))
    dataProc=interpBadCol(dataProc,iParms[str(agcid + 1)]['badCols'])

    # process the images and subtract the backgrounds
    _data1 = dataProc[region[2]:region[3],region[0]:region[1]].astype('float', copy=True, order="C")
    _data2 = dataProc[region[6]:region[7],region[4]:region[5]].astype('float', copy=True, order="C")
    bgClass1 = sep.Background(_data1)
    background1 = bgClass1.back()
    bgClass2 = sep.Background(_data2)
    background2 = bgClass2.back()
    
    newData = dataProc.copy()
    newData[region[2]:region[3],region[0]:region[1]]-=background1
    newData[region[6]:region[7],region[4]:region[5]]-=background2

    # array for the results. It's set to the number of reference points
    nElem = len(xPos)
    result = np.zeros(nElem, dtype=spotDtype)

    fx=5
    fy=5
    #first, get the new positions (also flags for saturation and position, background value and peak_intensity values
    
    for k in range(len(xPos)):

        # two templates, for glass and non glass
        xP = xPos[k]
        yP = yPos[k]
        if(xP <= 536):
            newPos, pPos, pVal, flag = fitTemplate(templateL, newData, (xP,yP), gridSize)
            result['background'][k] = background1[int(yP)-region[2], int(xP)-region[0]]

            #edge flag
            if(np.any([newPos[0]-2*fx < 0, newPos[1]+2*fx > (region[1]-region[0]),newPos[1]-2*fy < 0, newPos[1]+2*fy > (region[3]-region[2])],axis=0)):
                result['flags'][k] += 2


        else:
            newPos, pPos, pVal, flag = fitTemplate(templateR, newData, (xP,yP), gridSize)
            result['background'][k] = background2[int(yP)-region[6], int(xP)-region[4]]
            

            #side flag
            result['flags'][k]+=1
            
            #edge flag
            if(np.any([newPos[0]-2*fx < 0, newPos[1]+2*fx > (region[5]-region[4]),newPos[1]-2*fy < 0, newPos[1]+2*fy > (region[7]-region[6])],axis=0)):
                result['flags'][k] += 2

        #update the array
        result['centroid_x_pix'][k]=newPos[0]
        result['centroid_y_pix'][k]=newPos[1]
        result['flags'][k] += flag
        result['peak_pixel_x_pix'][k]=pPos[0]
        result['peak_pixel_x_pix'][k]=pPos[1]
        result['peak_intensity'] = pVal

        

        # now the windowed second moments; need to think about what values when this doesn't converge??
        xv,yv, xyv, conv = windowedFWHM(newData, newPos[0], newPos[1])
        if(conv == 0):
            result['central_image_moment_02_pix'][k]=xv
            result['central_image_moment_20_pix'][k]=yv
            result['central_image_moment_11_pix'][k]=xyv
        else:
            result['central_image_moment_02_pix'][k]=0
            result['central_image_moment_20_pix'][k]=0
            result['central_image_moment_11_pix'][k]=0
        result['flags'][k] += conv
            

    #result['image_moment_00_pix'][nSpots1:nElem] = spots2['flux']
    return result

    
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

    # keep the original value of the data for determining saturation later
    dataProc=subOverscan(data.astype('float'))
    dataProc=interpBadCol(dataProc,iParms[str(agcid + 1)]['badCols'])

    _data1 = dataProc[region[2]:region[3],region[0]:region[1]].astype('float', copy=True, order="C")
    _data2 = dataProc[region[6]:region[7],region[4]:region[5]].astype('float', copy=True, order="C")

    spots1, nSpots1, background1 = centroidRegion(_data1, thresh, minarea=minarea, deblend=deblend)
    spots2, nSpots2, background2 = centroidRegion(_data2, thresh, minarea=minarea, deblend=deblend)

    
    nElem = nSpots1 + nSpots2
    result = np.zeros(nElem, dtype=spotDtype)

    # flag spots near edge of region

    # dynamic fwhm calculation is overenthusiastic with out of focus images
    fx=5
    fy=5
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
        starPos:  position of star from focussed image (pixels)
        gridSize: size of grid to compute x-corr over
    
    output: 
        newPos: updated position
        sat: flag for saturated star
    """
    
    # get the size of the t
    tSize = template.shape[0]
    
    # half point of template/grid
    g2 = gridSize // 2
    t2 = tSize // 2
   
    #integer values of star position
    xcI = int(np.round(starPos[0]))
    ycI = int(np.round(starPos[1]))

    # subimage centred on the star position
    dSub = data[ycI-g2:ycI+g2+1,xcI-g2:xcI+g2+1]

    flag = 0

    # do the correlation
    sumVal=signal.correlate2d(dSub, np.flipud(np.fliplr(template)),mode='same')
    # if we don't have enough pixels to do the correlation, return original position, set flag
    if(np.array(dSub.shape).min()==0):
        newPos = starPos
        flag = flag + 32
        return newPos, [0,0], 0, flag

    # get the position and value of the maximum pixel
    pPos = np.array(np.unravel_index(dSub.argmax(),(gridSize,gridSize)))+np.array([g2,g2])
    pVal = dSub.max()

    #find the offset of the max value from the centre of the grid
    offset = np.array(np.unravel_index(sumVal.argmax(),(gridSize,gridSize)))-g2
    offseta = np.array(np.unravel_index(sumVal.argmax(),(gridSize,gridSize)))

    # now we apply a sub-pixel parabolic interpolation over the centre of the
    # cross correlation function to find the true maximum.



    l1 = -0
    l2 = +0

    i1=0
    i2=1

    yy=np.zeros((sumVal.shape[0]))
    for i in range(l1,l2+1):
        yy = yy+ sumVal[:,offseta[i1]+i]
    xx = np.arange(-g2,g2+1)

    fflag=0
    # try/except is because curve_fit crashes if it doesn't converge
    try:
        popt,pcov = curve_fit(parabola,xx[offseta[i1]-2:offseta[i1]+2+1], yy[offseta[i1]-2:offseta[i1]+2+1],p0=[-5,0.1,1e3])
        cX = popt[1]
    except:
        cX = offset[0]
        fflag=64
        
        
    yy=np.zeros((sumVal.shape[1]))
    for i in range(l1,l2+1):
        yy = yy+ sumVal[offseta[i2]+i,:]
    
    xx = np.arange(-g2,g2+1)

    try:
        popt,pcov = curve_fit(parabola,xx[offseta[i2]-2:offseta[i2]+3], yy[offseta[i2]-2:offseta[i2]+3],p0=[-5,0.1,1e3])
        
        cY = popt[1]
    except:
        cY = offset[1]
        fflag=64

    #set flag if the sub-pixel interpolation didn't work
    flag = flag + fflag


    #apply the offset
    offset=[cX,cY]
    newPos = starPos + np.array([offset[1],offset[0]])


    return newPos, pPos, pVal, flag

           
def parabola(x,a,b,c):

    return a*(x-b)**2+c
