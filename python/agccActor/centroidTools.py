
import agccActor.windowedCentroid.centroid as centroid
from scipy.stats import sigmaclip
import yaml
import os
import numpy as np

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


def getCentroids(image,cParms):

    # split into two halves
    
    lim1a=28
    lim1b=548
    lim2a=507
    lim2b=1042
    
    #get thresholds 
    a1,b2,c2=sigmaclip(image[:,lim1a:lim2a],cParms['threshSigma'],cParms['threshSigma'])
    a2,b2,c2=sigmaclip(image[:,lim1b:lim2b],cParms['threshSigma'],cParms['threshSigma'])
    
    #return the mean + sigma value
    threshFind1=a1.std()*cParms['findSigma']
    threshCent1=a1.std()*cParms['centSigma']
    globalBack1=np.median(a1)

    threshFind2=a2.std()*cParms['findSigma']
    threshCent2=a2.std()*cParms['centSigma']
    globalBack2=np.median(a2)

    # centroid

    res1=centroid.centroid_only(image[:,lim1a:lim2a].astype('<i4')-int(globalBack1),cParms['fwhmx'],cParms['fwhmy'],threshFind1,threshCent1,cParms['boxFind'],cParms['boxCent'],cParms['nmin'],cParms['nmax'],cParms['maxIt'],0,0)

    res2=centroid.centroid_only(image[:,lim1b:lim2b].astype('<i4')-int(globalBack2),cParms['fwhmx'],cParms['fwhmy'],threshFind2,threshCent2,cParms['boxFind'],cParms['boxCent'],cParms['nmin'],cParms['nmax'],cParms['maxIt'],0,0)

    
    #reformat
    centroids1=np.frombuffer(res1,dtype='<f8')
    centroids1=np.reshape(centroids1,(len(centroids1)//11,11))
    centroids1[:,0]+=lim1a
    nSpots1=centroids1.shape[0]

    centroids2=np.frombuffer(res2,dtype='<f8')
    centroids2=np.reshape(centroids2,(len(centroids2)//11,11))
    centroids2[:,0]+=lim1b
    nSpots2=centroids2.shape[0]

    # reassemble into two regions
    points=np.empty((nSpots1+nSpots2,12))

    points[0:nSpots1,0]=np.arange(nSpots1)
    points[nSpots1:nSpots1+nSpots2,0]=np.arange(nSpots2)+nSpots1

    points[0:nSpots1,1:]=centroids1[:,0:]
    points[nSpots1:nSpots1+nSpots2,1:]=centroids2[:,0:]

    ind=np.where(points[:,1]==points[:,1])
    
    return points[ind,:]

    
