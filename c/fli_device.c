//
// FLI camera library
//

#include <Python.h>
#include "structmember.h"
#include <numpy/arrayobject.h>
#include <stdio.h>
#include <stdlib.h>
#include <strings.h>
#include "libfli-1.104/libfli.h"

#define SetError(msg) {                         \
      PyErr_SetString(PyExc_RuntimeError, msg); \
      return NULL;                              \
   }
#define HandleResult(res,msg) if(res!=0) SetError(msg)

#define MAX_DEVICES 32
#define BUFF_SIZE 1024
#define LIBVERSIZE 1024
#define MAX_PATH 256
#define NFLUSHES 3

static int numCams = 0;
static flidev_t dev[MAX_DEVICES];
static char *listName[MAX_DEVICES];
static long listDomain[MAX_DEVICES];
static char libver[LIBVERSIZE];
static int xsize[MAX_DEVICES];
static int ysize[MAX_DEVICES];

/*
static char model[MAX_PATH];
static char serialNum[MAX_PATH];
static char HWRevision[MAX_PATH];
static char FWRevision[MAX_PATH];
static float pixelSizeX, pixelSizeY;
static int arrayAreaX0, arrayAreaY0, arrayAreaX1, arrayAreaY1;
static int visibleAreaX0, visibleAreaY0, visibleAreaX1, visibleAreaY1;
*/

void EnumerateCameras(void);

// Retrieve available USB camera information

void EnumerateCameras(void)
{
   char file[MAX_PATH], name[MAX_PATH];
   long domain;

   FLICreateList(FLIDOMAIN_USB | FLIDEVICE_CAMERA);

   numCams = 0;
   if(FLIListFirst(&domain, file, MAX_PATH, name, MAX_PATH) == 0) {
      do {
         if(listName[numCams] != NULL)
            free(listName[numCams]);
         listName[numCams] = (char *) malloc(strlen(file) + 1);
         strcpy(listName[numCams], file);
         listDomain[numCams] = domain;
         numCams++;
      } while((FLIListNext(&domain, file, MAX_PATH, name, MAX_PATH) == 0)
              && (numCams < MAX_DEVICES));
   }

   FLIDeleteList();
}

// Get library version

static PyObject *FLI_getLibVersion(PyObject * self)
{
   return Py_BuildValue("s", libver);
}

// Get number of camera devices

static PyObject *FLI_numberOfCamera(PyObject * self)
{
   return Py_BuildValue("i", numCams);
}

// Open camera

static PyObject *FLI_open(PyObject * self, PyObject * args)
{
   int n_dev, res;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] != FLI_INVALID_DEVICE)
      Py_RETURN_NONE;

   if(n_dev >= numCams)
      SetError("Camera not available");

   printf("Connecting to camera '%s' with domain '%ld'\n", listName[n_dev],
          listDomain[n_dev]);

   res = FLIOpen(&dev[n_dev], listName[n_dev], listDomain[n_dev]);
   HandleResult(res, "FLIOpen failed");

   res = FLIControlBackgroundFlush(dev[n_dev], FLI_BGFLUSH_START);
   HandleResult(res, "FLIControlBackgroundFlush failed");
//   res = FLISetNFlushes(dev[n_dev], NFLUSHES);
//   HandleResult(res, "FLISetNFlushes failed");

   Py_RETURN_NONE;
}

// Close camera

static PyObject *FLI_close(PyObject * self, PyObject * args)
{
   int n_dev;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      Py_RETURN_NONE;

   FLIClose(dev[n_dev]);
   dev[n_dev] = FLI_INVALID_DEVICE;

   Py_RETURN_NONE;
}

// Get camera Model

static PyObject *FLI_getModel(PyObject * self, PyObject * args)
{
   int n_dev, res;
   char buff[BUFF_SIZE];

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetModel(dev[n_dev], buff, BUFF_SIZE);
   HandleResult(res, "FLIGetModel failed");

   return Py_BuildValue("s", buff);
}

// Get camera serial number

static PyObject *FLI_getSerial(PyObject * self, PyObject * args)
{
   int n_dev, res;
   char buff[BUFF_SIZE];

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetSerialString(dev[n_dev], buff, BUFF_SIZE);
   HandleResult(res, "FLIGetSerialString failed");

   return Py_BuildValue("s", buff);
}

// Get camera HW revision

static PyObject *FLI_getHWRevision(PyObject * self, PyObject * args)
{
   int n_dev, res;
   long rev;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetHWRevision(dev[n_dev], &rev);
   HandleResult(res, "FLIGetHWRevision failed");

   return Py_BuildValue("l", rev);
}

// Get camera FW revision

static PyObject *FLI_getFWRevision(PyObject * self, PyObject * args)
{
   int n_dev, res;
   long rev;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetFWRevision(dev[n_dev], &rev);
   HandleResult(res, "FLIGetFWRevision failed");

   return Py_BuildValue("l", rev);
}

// Get pixel size

static PyObject *FLI_getPixelSize(PyObject * self, PyObject * args)
{
   int n_dev, res;
   double d1, d2;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetPixelSize(dev[n_dev], &d1, &d2);
   HandleResult(res, "FLIGetPixelSize failed");

   return Py_BuildValue("(dd)", d1, d2);
}

// Get array area

static PyObject *FLI_getArrayArea(PyObject * self, PyObject * args)
{
   int n_dev, res;
   long x1, y1, x2, y2;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetArrayArea(dev[n_dev], &x1, &y1, &x2, &y2);
   HandleResult(res, "FLIGetArrayArea failed");

   return Py_BuildValue("(llll)", x1, y1, x2, y2);
}

// Get visible area

static PyObject *FLI_getVisibleArea(PyObject * self, PyObject * args)
{
   int n_dev, res;
   long x1, y1, x2, y2;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetVisibleArea(dev[n_dev], &x1, &y1, &x2, &y2);
   HandleResult(res, "FLIGetVisibleArea failed");

   return Py_BuildValue("(llll)", x1, y1, x2, y2);
}

// Set image area

static PyObject *FLI_setImageArea(PyObject * self, PyObject * args)
{
   int n_dev, res;
   long x1, y1, x2, y2;

   if(!PyArg_ParseTuple(args, "illll", &n_dev, &x1, &y1, &x2, &y2))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLISetImageArea(dev[n_dev], x1, y1, x2, y2);
   HandleResult(res, "FLISetImageArea failed");

   xsize[n_dev] = x2 - x1;
   ysize[n_dev] = y2 - y1;

   Py_RETURN_NONE;
}

// Set temperature

static PyObject *FLI_setTemperature(PyObject * self, PyObject * args)
{
   int n_dev, exptime, res;

   if(!PyArg_ParseTuple(args, "ii", &n_dev, &exptime))
      return NULL;
   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("camera not found or not opened");

   res = FLISetTemperature(dev[n_dev], exptime);
   HandleResult(res, "FLISetTemperature failed");

   Py_RETURN_NONE;
}

// Read temperature

static PyObject *FLI_getTemperature(PyObject * self, PyObject * args)
{
   int n_dev, res;
   double temp;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetTemperature(dev[n_dev], &temp);
   HandleResult(res, "FLIGetTemperature failed");

   return Py_BuildValue("d", temp);
}

// Get cooler power

static PyObject *FLI_getCoolerPower(PyObject * self, PyObject * args)
{
   int n_dev, res;
   double d;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetCoolerPower(dev[n_dev], &d);
   HandleResult(res, "FLIGetCoolerPower failed");

   return Py_BuildValue("d", d);
}

// Set exposure parameter

static PyObject *FLI_setExposure(PyObject * self, PyObject * args)
{
   int n_dev, exptime, res;

   if(!PyArg_ParseTuple(args, "ii", &n_dev, &exptime))
      return NULL;
   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("camera not found or not opened");

   // Setting "exposure" parameter in millisecond
   res = FLISetExposureTime(dev[n_dev], exptime);
   HandleResult(res, "FLISetExposureTime failed");

   Py_RETURN_NONE;
}

// Set frame type

static PyObject *FLI_setFrameType(PyObject * self, PyObject * args)
{
   int n_dev, f_type, res;

   if(!PyArg_ParseTuple(args, "ii", &n_dev, &f_type))
      return NULL;
   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("camera not found or not opened");

   // Setting frame type
   res = FLISetFrameType(dev[n_dev], f_type);
   HandleResult(res, "FLISetFrameType failed");

   Py_RETURN_NONE;
}

// Set H-binning

static PyObject *FLI_setHBin(PyObject * self, PyObject * args)
{
   int n_dev, hbin, res;

   if(!PyArg_ParseTuple(args, "ii", &n_dev, &hbin))
      return NULL;
   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("camera not found or not opened");

   // Setting H-binning
   res = FLISetHBin(dev[n_dev], hbin);
   HandleResult(res, "FLISetHBin failed");

   Py_RETURN_NONE;
}

// Set V-binning

static PyObject *FLI_setVBin(PyObject * self, PyObject * args)
{
   int n_dev, vbin, res;

   if(!PyArg_ParseTuple(args, "ii", &n_dev, &vbin))
      return NULL;
   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("camera not found or not opened");

   // Setting H-binning
   res = FLISetVBin(dev[n_dev], vbin);
   HandleResult(res, "FLISetVBin failed");

   Py_RETURN_NONE;
}

// Do exposure

static PyObject *FLI_expose(PyObject * self, PyObject * args)
{
   int n_dev, res;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;
   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("camera not found or not opened");

   // Setting H-binning
   res = FLIExposeFrame(dev[n_dev]);
   HandleResult(res, "FLIExposeFrame failed");

   Py_RETURN_NONE;
}

// Set TDI rate

static PyObject *FLI_setTDI(PyObject * self, PyObject * args)
{
   int n_dev, tdi, res;

   if(!PyArg_ParseTuple(args, "ii", &n_dev, &tdi))
      return NULL;
   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("camera not found or not opened");

   // Setting TDI rate
   res = FLISetTDI(dev[n_dev], tdi, 0);
   HandleResult(res, "FLISetTDI failed");

   Py_RETURN_NONE;
}

// Get device status

static PyObject *FLI_getDevStatus(PyObject * self, PyObject * args)
{
   int n_dev, res;
   long status;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetDeviceStatus(dev[n_dev], &status);
   HandleResult(res, "FLIGetDeviceStatus failed");

   return Py_BuildValue("l", status);
}

// Get exposure status

static PyObject *FLI_getExpStatus(PyObject * self, PyObject * args)
{
   int n_dev, res;
   long t;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetExposureStatus(dev[n_dev], &t);
   HandleResult(res, "FLIGetExposureStatus failed");

   return Py_BuildValue("l", t);
}

// Check if expose finish

static PyObject *FLI_isDataReady(PyObject * self, PyObject * args)
{
   int n_dev, res, isReady;
   long t, status;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetDeviceStatus(dev[n_dev], &status);
   HandleResult(res, "FLIGetDeviceStatus failed");
   res = FLIGetExposureStatus(dev[n_dev], &t);
   HandleResult(res, "FLIGetExposureStatus failed");
   isReady = ((status == FLI_CAMERA_STATUS_UNKNOWN) && (t == 0)) ||
       ((status != FLI_CAMERA_STATUS_UNKNOWN) &&
        (status & FLI_CAMERA_DATA_READY) != 0);

   if(isReady)
      Py_RETURN_TRUE;
   else
      Py_RETURN_FALSE;
}

// Grab image

static PyObject *FLI_grabImage(PyObject * self, PyObject * args)
{
   int n_dev, res, row, col, isReady, i;
   long status, t;
   unsigned short *img;
   npy_intp dims[2];

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   do {
      res = FLIGetDeviceStatus(dev[n_dev], &status);
      HandleResult(res, "FLIGetDeviceStatus failed");
      res = FLIGetExposureStatus(dev[n_dev], &t);
      HandleResult(res, "FLIGetExposureStatus failed");
      isReady = ((status == FLI_CAMERA_STATUS_UNKNOWN) && (t == 0)) ||
          ((status != FLI_CAMERA_STATUS_UNKNOWN) &&
          (status & FLI_CAMERA_DATA_READY) != 0);
      if(!isReady) {
         t *= 1000;
         if(usleep((t > 200000) ? 200000 : t + 1000) < 0)
            SetError("usleep call failed");
      } else
         break;
   } while(1);

   col = xsize[n_dev];
   row = ysize[n_dev];
   img = (unsigned short *)malloc(col * row * 2);
   if(img == NULL)
      SetError("malloc call failed");
   for(i = 0; i < row; i++) {
      res = FLIGrabRow(dev[n_dev], &img[i * col], col);
      HandleResult(res, "FFLIGrabRow failed");
   }

   dims[0] = row;
   dims[1] = col;
   return PyArray_SimpleNewFromData(2, dims, PyArray_UINT16, img);
}

// Cancel an exposure

static PyObject *FLI_cancelExposure(PyObject * self, PyObject * args)
{
   int n_dev, res;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      Py_RETURN_NONE;

   res = FLIEndExposure(dev[n_dev]);
   HandleResult(res, "FLIEndExposure failed");

   Py_RETURN_NONE;
}

// Check if camera is ready

static PyObject *FLI_isCameraReady(PyObject * self, PyObject * args)
{
   int n_dev, res, isReady;
   long t, status;

   if(!PyArg_ParseTuple(args, "i", &n_dev))
      return NULL;

   if(dev[n_dev] == FLI_INVALID_DEVICE)
      SetError("Camera not available");

   res = FLIGetDeviceStatus(dev[n_dev], &status);
   HandleResult(res, "FLIGetDeviceStatus failed");
   res = FLIGetExposureStatus(dev[n_dev], &t);
   HandleResult(res, "FLIGetExposureStatus failed");
   isReady = ((status == FLI_CAMERA_STATUS_UNKNOWN) && (t == 0)) ||
       ((status != FLI_CAMERA_STATUS_UNKNOWN) &&
        (status & FLI_CAMERA_STATUS_MASK) == FLI_CAMERA_STATUS_IDLE);

   if(isReady)
      Py_RETURN_TRUE;
   else
      Py_RETURN_FALSE;
}

static PyMethodDef FLI_methods[] = {
   {"numberOfCamera", (PyCFunction) FLI_numberOfCamera, METH_NOARGS,
    "Get the number of available cameras"},
   {"getLibVersion", (PyCFunction) FLI_getLibVersion, METH_NOARGS,
    "Get library version"},
   {"open", (PyCFunction) FLI_open, METH_VARARGS, "Open camera device"},
   {"close", (PyCFunction) FLI_close, METH_VARARGS, "Close camera device"},
   {"getModel", (PyCFunction) FLI_getModel, METH_VARARGS, "Get camera model"},
   {"getSerial", (PyCFunction) FLI_getSerial, METH_VARARGS,
    "Get serial number"},
   {"getHWRevision", (PyCFunction) FLI_getHWRevision, METH_VARARGS,
    "Get HW revision"},
   {"getFWRevision", (PyCFunction) FLI_getFWRevision, METH_VARARGS,
    "Get FW revision"},
   {"getPixelSize", (PyCFunction) FLI_getPixelSize, METH_VARARGS,
    "Get pixel size"},
   {"getArrayArea", (PyCFunction) FLI_getArrayArea, METH_VARARGS,
    "Get array area"},
   {"getVisibleArea", (PyCFunction) FLI_getVisibleArea, METH_VARARGS,
    "Get visible area"},
   {"setImageArea", (PyCFunction) FLI_setImageArea, METH_VARARGS,
    "Set image area"},
   {"setTemperature", (PyCFunction) FLI_setTemperature, METH_VARARGS,
    "Set temperature"},
   {"getTemperature", (PyCFunction) FLI_getTemperature, METH_VARARGS,
    "Read temperature"},
   {"getCoolerPower", (PyCFunction) FLI_getCoolerPower, METH_VARARGS,
    "Get cooler power"},
   {"setExposure", (PyCFunction) FLI_setExposure, METH_VARARGS,
    "Set expose time in ms"},
   {"setFrameType", (PyCFunction) FLI_setFrameType, METH_VARARGS,
    "Set frame type"},
   {"setHBin", (PyCFunction) FLI_setHBin, METH_VARARGS, "Set H-binning"},
   {"setVBin", (PyCFunction) FLI_setVBin, METH_VARARGS, "Set V-binning"},
   {"expose", (PyCFunction) FLI_expose, METH_VARARGS, "Do exposure"},
   {"setTDI", (PyCFunction) FLI_setTDI, METH_VARARGS, "Set TDI rate"},
   {"getDevStatus", (PyCFunction) FLI_getDevStatus, METH_VARARGS,
    "Get device status"},
   {"getExpStatus", (PyCFunction) FLI_getExpStatus, METH_VARARGS,
    "Get exposure status"},
   {"isDataReady", (PyCFunction) FLI_isDataReady, METH_VARARGS,
    "Check if expose finish"},
   {"grabImage", (PyCFunction) FLI_grabImage, METH_VARARGS, "Grab image"},
   {"cancelExposure", (PyCFunction) FLI_cancelExposure, METH_VARARGS,
    "Cancel an exposure"},
   {"isCameraReady", (PyCFunction) FLI_isCameraReady, METH_VARARGS,
    "Check if camera is ready"},
   {NULL, NULL, 0, NULL}
};

#ifndef PyMODINIT_FUNC          /* declarations for DLL import/export */
#define PyMODINIT void
#endif

PyMODINIT_FUNC initfli_device(void)
{
   PyObject *m;
   int i;

   for(i = 0; i < MAX_DEVICES; i++) {
      dev[i] = FLI_INVALID_DEVICE;
      listName[i] = NULL;
      xsize[i] = 0;
      ysize[i] = 0;
   }
   FLISetDebugLevel(NULL, FLIDEBUG_FAIL);
   if(FLIGetLibVersion(libver, LIBVERSIZE) != 0) {
      printf("FLIGetLibVersion failed\n");
      return;
   }
   EnumerateCameras();
   m = Py_InitModule("fli_device", FLI_methods);
   if(m == NULL)
      return;
   PyModule_AddIntConstant(m, "FRAME_TYPE_NORMAL", FLI_FRAME_TYPE_NORMAL);
   PyModule_AddIntConstant(m, "FRAME_TYPE_DARK", FLI_FRAME_TYPE_DARK);
   PyModule_AddIntConstant(m, "FRAME_TYPE_FLOOD", FLI_FRAME_TYPE_FLOOD);
   PyModule_AddIntConstant(m, "FRAME_TYPE_RBI_FLUSH",
                           FLI_FRAME_TYPE_RBI_FLUSH);
   PyModule_AddIntConstant(m, "CAMERA_STATUS_UNKNOWN",
                           FLI_CAMERA_STATUS_UNKNOWN);
   PyModule_AddIntConstant(m, "CAMERA_STATUS_IDLE", FLI_CAMERA_STATUS_IDLE);
   PyModule_AddIntConstant(m, "CAMERA_STATUS_MASK", FLI_CAMERA_STATUS_MASK);
   PyModule_AddIntConstant(m, "CAMERA_CAMERA_STATUS_WAITING_FOR_TRIGGER",
                           FLI_CAMERA_STATUS_WAITING_FOR_TRIGGER);
   PyModule_AddIntConstant(m, "CAMERA_STATUS_EXPOSING",
                           FLI_CAMERA_STATUS_EXPOSING);
   PyModule_AddIntConstant(m, "CAMERA_STATUS_READING_CCD",
                           FLI_CAMERA_STATUS_READING_CCD);
   PyModule_AddIntConstant(m, "CAMERA_DATA_READY", FLI_CAMERA_DATA_READY);
   import_array();
}
