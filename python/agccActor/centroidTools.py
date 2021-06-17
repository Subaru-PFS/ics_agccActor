
import agccActor.windowedCentroid.centroid as centroid
from scipy.stats import sigmaclip
import yaml
import os
import numpy as np

def getCentroids(image):

    aa=open("check.txt","w")
    print("here",file=aa)
    aa.close()
    aa=open("check.txt","a")

    path = os.path.join(os.environ['ICS_AGCCACTOR_DIR'],"etc","agccDefaultCentroidParameters.yaml")
    print(path,file=aa)
    aa.close()
    aa=open("check.txt","a")

    with open(path, 'r') as inFile:
        defaultParms=yaml.safe_load(inFile)
    centParam=defaultParms['values']
    
    print(centParam,file=aa)
    aa.close()
    aa=open("check.txt","a")
    
    #get thresholds
    a,b,c=sigmaclip(image,centParam['threshSigma'],centParam['threshSigma'])
    
    #return the mean + sigma value
    threshFind=a.std()*centParam['findSigma']
    threshCent=a.std()*centParam['centSigma']
    globalBack=a.mean()
    print(threshFind,threshCent,globalBack,file=aa)
    aa.close()
    
    #centroid

    print(centParam['fwhmx'],centParam['fwhmy'],threshFind,threshCent,centParam['boxFind'],centParam['boxCent'],centParam['nmin'],centParam['nmax'],centParam['maxIt'],globalBack,0)
    a=centroid.centroid_only(image.astype('<i4')-int(globalBack),centParam['fwhmx'],centParam['fwhmy'],threshFind,threshCent,centParam['boxFind'],centParam['boxCent'],centParam['nmin'],centParam['nmax'],centParam['maxIt'],0,0)
    
    #reformat
    centroids=np.frombuffer(a,dtype='<f8')
    centroids=np.reshape(centroids,(len(centroids)//11,11))
    nSpots=centroids.shape[0]
    points=np.empty((nSpots,12))
    points[:,0]=np.arange(nSpots)
    points[:,1:]=centroids[:,0:]
    return points

    
