"""FLI USB camera library"""

cdef extern from "libfli.h" nogil:

    ctypedef long flidev_t
    ctypedef long flidomain_t
    ctypedef long fliframe_t
    ctypedef long flidebug_t
    ctypedef long flimode_t
    ctypedef long flistatus_t
    ctypedef long flibgflush_t
    ctypedef long flitdirate_t
    ctypedef long flitdiflags_t
    ctypedef long LIBFLIAPI

    int FLI_INVALID_DEVICE
    int FLIDOMAIN_USB
    int FLIDEVICE_CAMERA
 
    int FLI_FRAME_TYPE_NORMAL
    int FLI_FRAME_TYPE_DARK
    int FLI_FRAME_TYPE_FLOOD
    int FLI_FRAME_TYPE_RBI_FLUSH

    int FLIDEBUG_NONE
    int FLIDEBUG_INFO
    int FLIDEBUG_WARN
    int FLIDEBUG_FAIL
    int FLIDEBUG_IO
    int FLIDEBUG_ALL

    int FLI_CAMERA_STATUS_UNKNOWN
    int FLI_CAMERA_STATUS_MASK
    int FLI_CAMERA_STATUS_IDLE
    int FLI_CAMERA_STATUS_WAITING_FOR_TRIGGER
    int FLI_CAMERA_STATUS_EXPOSING
    int FLI_CAMERA_STATUS_READING_CCD
    int FLI_CAMERA_DATA_READY

    int FLI_BGFLUSH_STOP
    int FLI_BGFLUSH_START

    LIBFLIAPI FLICreateList(flidomain_t domain)
    LIBFLIAPI FLIDeleteList()
    LIBFLIAPI FLIListFirst(flidomain_t *domain, char *filename,
                           size_t fnlen, char *name, size_t namelen)
    LIBFLIAPI FLIListNext(flidomain_t *domain, char *filename,
                          size_t fnlen, char *name, size_t namelen)
    LIBFLIAPI FLIOpen(flidev_t *dev, char *name, flidomain_t domain)
    LIBFLIAPI FLISetDebugLevel(char *host, flidebug_t level)
    LIBFLIAPI FLIClose(flidev_t dev)
    LIBFLIAPI FLIGetLibVersion(char* ver, size_t len)
    LIBFLIAPI FLIGetModel(flidev_t dev, char* model, size_t len)
    LIBFLIAPI FLIGetPixelSize(flidev_t dev, double *pixel_x, double *pixel_y)
    LIBFLIAPI FLIGetHWRevision(flidev_t dev, long *hwrev)
    LIBFLIAPI FLIGetFWRevision(flidev_t dev, long *fwrev)
    LIBFLIAPI FLIGetArrayArea(flidev_t dev, long* ul_x, long* ul_y, long* lr_x, long* lr_y)
    LIBFLIAPI FLIGetVisibleArea(flidev_t dev, long* ul_x, long* ul_y, long* lr_x, long* lr_y)
    LIBFLIAPI FLISetExposureTime(flidev_t dev, long exptime)
    LIBFLIAPI FLISetImageArea(flidev_t dev, long ul_x, long ul_y, long lr_x, long lr_y)
    LIBFLIAPI FLISetHBin(flidev_t dev, long hbin)
    LIBFLIAPI FLISetVBin(flidev_t dev, long vbin)
    LIBFLIAPI FLISetFrameType(flidev_t dev, fliframe_t frametype)
    LIBFLIAPI FLICancelExposure(flidev_t dev)
    LIBFLIAPI FLIGetExposureStatus(flidev_t dev, long *timeleft)
    LIBFLIAPI FLISetTemperature(flidev_t dev, double temperature)
    LIBFLIAPI FLIGetTemperature(flidev_t dev, double *temperature)
    LIBFLIAPI FLIGetCoolerPower(flidev_t dev, double *power)
    LIBFLIAPI FLIGrabRow(flidev_t dev, void *buff, size_t width)
    LIBFLIAPI FLIExposeFrame(flidev_t dev)
    LIBFLIAPI FLIFlushRow(flidev_t dev, long rows, long repeat)
    LIBFLIAPI FLISetNFlushes(flidev_t dev, long nflushes)
    LIBFLIAPI FLIControlBackgroundFlush(flidev_t dev, flibgflush_t bgflush)
    LIBFLIAPI FLIGetDeviceStatus(flidev_t dev, long *status)
    LIBFLIAPI FLIGetCameraModeString(flidev_t dev, flimode_t mode_index, char *mode_string, size_t siz)
    LIBFLIAPI FLIGetCameraMode(flidev_t dev, flimode_t *mode_index)
    LIBFLIAPI FLISetCameraMode(flidev_t dev, flimode_t mode_index)
    LIBFLIAPI FLIGetSerialString(flidev_t dev, char* serial, size_t len)
    LIBFLIAPI FLIEndExposure(flidev_t dev)
    LIBFLIAPI FLISetTDI(flidev_t dev, flitdirate_t tdi_rate, flitdiflags_t flags)

cdef enum:
    MAX_DEVICES = 32
    MAX_PATH = 256
    BUFF_SIZE = 1024
    LIBVERSIZE = 1024
    NFLUSHES = 3

cdef:
    int numCams
    flidev_t dev[MAX_DEVICES]
    char *listName[MAX_DEVICES]
    long listDomain[MAX_DEVICES]
    char libver[LIBVERSIZE]
    unsigned short *buffer[MAX_DEVICES]

