from centroid import centroid_only
from astropy.io.fits import getdata
import numpy as np
import matplotlib.pyplot as plt
import os
#image=getdata('/Users/karr/Science/PFS/Firsts/PFSC00366600.fits')
image=getdata('/Users/karr/Aug19/Day3/PFSC01578800.fits')

os.system('date')
for i in range(1):
    #a=centroid_only(np.ascontiguousarray(image.astype('<i4')[2000:6000,2500:7000]),0,0,1725,1300,10,6,10,90,20,0)
    a=centroid_only(image.astype('<i4'),0,0,1725,1300,10,6,10,90,20,1)
    centroids=np.frombuffer(a,dtype='<f8')
    centroids=np.reshape(centroids,(len(centroids)//7,7))
    
    #ind=np.where(centroids[:,1] < 1000)
    #print(centroids[ind,0],centroids[ind,1])

    print(centroids[:,0].min(),centroids[:,0].max(),centroids[:,1].min(), centroids[:,1].max())
    for j in range(100):
        print(centroids[j,0],centroids[j,1],centroids[j,2],centroids[j,3],centroids[j,4],centroids[j,5])
    
os.system('date')
print(centroids.shape)
plt.ion()
fig,ax=plt.subplots()
ax.scatter(centroids[:,0],centroids[:,1])
fig.show()
plt.savefig("cent.png")

