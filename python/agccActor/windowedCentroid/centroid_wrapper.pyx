
from cpython cimport array
import array
from cython cimport view
import astropy.io.fits as pyfits
import numpy as np
cimport numpy as np
import ctypes
from libc.stdlib cimport free

cdef extern from "centroid_types.h" nogil:
        struct centroids:
                double x;
                double y;
                double x2;
                double y2;
                double xy;
                double peak;
                double back;
                double xpeak;
                double ypeak;
                double flux;

cdef extern from "centroid_types.h" nogil:
        struct fibreid:
                double xp;     
                double yp;               
                double xt;                
                double yt;       
                double xc;       
                double yc;       
                double x;       
                double y;       
                double peak;
                double back;
                double fx;
                double fy;
                int qual;
                int idnum;       
    

cdef extern from "centroid.h" nogil:
     centroids *centroid(int *image, int n_x, int n_y, int thresh1, int thresh2, double fwhmx, double fwhmy,int boxFind, int boxCent,int *npoint, int nmin, int nmax,int maxIt, int globalBack, int verbose)

def centroid_only(np.ndarray[int, ndim=2, mode="c"] image, double fwhmx, double fwhmy, int thresh1, int thresh2, int boxFind, int boxCent,int nmin, int nmax, int maxIt,int globalBack, int verbose):

    """

    Take an image, return the centroids
        
    """ 

    cdef centroids *vals
    cdef char *cp
    cdef int npoint[1]

    #The function call
    with nogil:
         vals=centroid(<int *>image.data,image.shape[1],image.shape[0],thresh1,thresh2,fwhmx,fwhmy, boxFind,boxCent, npoint, nmin,nmax,maxIt, globalBack, verbose)

    #convert the output into a buffer string
    cp = <char *> vals

    #and into a numpy record array
    
    result=np.frombuffer(cp[:sizeof(centroids) * npoint[0]],dtype=[('x','<f8'),('y','<f8'),('xpeak','<f8'),('ypeak','<f8'),('fx','<f8'),('fy','<f8'),('xy','<f8'),('peak','<f8'),('flux','<f8'),('back','<f8'),('npix','<f8')])

    result = np.copy(result)
    free(vals)

    return result
