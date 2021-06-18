
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

    aa=open("check.txt","w")
    print("here",file=aa)
    aa.close()
    aa=open("check.txt","a")

    #path = os.path.join(os.environ['ICS_AGCCACTOR_DIR'],"etc","agccDefaultCentroidParameters.yaml")
    #print(path,file=aa)
    #aa.close()
    #aa=open("check.txt","a")
    #
    #with open(path, 'r') as inFile:
    #    defaultParms=yaml.safe_load(inFile)
    #centParam=defaultParms['values']
    
    print(cParms,file=aa)
    aa.close()
    aa=open("check.txt","a")
    
    #get thresholds
    a,b,c=sigmaclip(image,cParms['threshSigma'],cParms['threshSigma'])
    
    #return the mean + sigma value
    threshFind=a.std()*cParms['findSigma']
    threshCent=a.std()*cParms['centSigma']
    globalBack=a.mean()
    print(threshFind,threshCent,globalBack,file=aa)
    aa.close()
    
    #centroid

    print(cParms['fwhmx'],cParms['fwhmy'],threshFind,threshCent,cParms['boxFind'],cParms['boxCent'],cParms['nmin'],cParms['nmax'],cParms['maxIt'],globalBack,0)
    a=centroid.centroid_only(image.astype('<i4')-int(globalBack),cParms['fwhmx'],cParms['fwhmy'],threshFind,threshCent,cParms['boxFind'],cParms['boxCent'],cParms['nmin'],cParms['nmax'],cParms['maxIt'],0,0)
    
    #reformat
    centroids=np.frombuffer(a,dtype='<f8')
    centroids=np.reshape(centroids,(len(centroids)//11,11))
    nSpots=centroids.shape[0]
    points=np.empty((nSpots,12))
    points[:,0]=np.arange(nSpots)
    points[:,1:]=centroids[:,0:]
    return points

    
