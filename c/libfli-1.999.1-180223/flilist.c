

#include <stdio.h>
#include <math.h>
#include <string.h>
#include <getopt.h>
#include <assert.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include <ncurses.h>	

#define WINTAKEPIC_VER "1.0.0"

#define USEFITS

#define MAX_DEVICES 32
#define BUFF_SIZE 1024
#define MAX_PATH 256

#include "libfli.h"

#define DOFLIAPI(F) { if ((status = (F)) != 0) { printf("%s failed in %s, line %d. status = %d\n", #F, __FILE__, __LINE__, status); ThreadState = TS_DONE; break; } }

#define LIBVERSIZE 1024

long status = 0;

int numCams = 0;
char *listName[MAX_DEVICES];
long listDomain[MAX_DEVICES];

void EnumerateCameras(flidomain_t enumDomain);


enum threadstate_t 
{
	TS_RBI_FLOOD,
	TS_RBI_FLUSH,
	TS_EXPOSING,
	TS_DOWNLOAD,
	TS_START_EXPOSURE,
	TS_DONE,
	TS_ABORT,
} ThreadState = TS_START_EXPOSURE;


// void usage(char *fmt, ...)
// {
// 	extern const char *__progname;
// 	va_list ap;

// 	va_start(ap, fmt);

// 	printf("\n");
// 	if(fmt != NULL)
// 	{
// 		vprintf(fmt, ap);
// 		printf("\n\n");
// 	}

// 	printf("Usage: wintakepic [-n <num pics>] [-h <hbin>] [-v <vbin>] [-x <exposure time in milliseconds>] [-t <tdi rate>] [-y <rbi exposure time in milliseconds>] [-r <rbi num flushes>] [-b <rbi bin>] <outfile basename>\n");

// 	va_end(ap);

// 	exit(0);
// }


int main(int argc, char *argv[])
{
	printf("====================\n");
	printf("FLI WinTakePic " WINTAKEPIC_VER " \n");

    int opt;
	int pics = 1, hbin = 1, vbin = 1, exptime = 500, rbiFlushes = 0, rbin = 1, rbiExposureTime = 500;
	int tdi_rate = 0;
	char *outfile, libver[LIBVERSIZE];

	////////////////////////////////////////////////

	if(FLIGetLibVersion(libver, LIBVERSIZE) != 0)
	{
		printf("Unable to retrieve library version!\n");
		exit(0);
	}

	printf("Library version '%s'\n", libver);

	EnumerateCameras(FLIDOMAIN_USB | FLIDEVICE_CAMERA);

	if(numCams == 0)
	{
		printf("\nNo FLI cameras have been detected\n");
	}

	flidev_t dev = FLI_INVALID_DEVICE;

	for(int i = 0; i < numCams; i++)
	{
		long tmp1, tmp2, tmp3, tmp4, img_rows, row_width;
		double d1, d2;
		char buff[BUFF_SIZE];
		unsigned short *img;
		int row;

		if(dev != FLI_INVALID_DEVICE)
		{
			FLIClose(dev);
			dev = FLI_INVALID_DEVICE;
		}

		printf("\nConnecting to camera '%s' with domain '%ld'\n", listName[i], listDomain[i]);

		DOFLIAPI(FLIOpen(&dev, listName[i], listDomain[i]));
		if(status != 0)
		{
			continue;
		}

		DOFLIAPI(FLIGetModel(dev, buff, BUFF_SIZE));
		printf("Model:        %s\n", buff);

		DOFLIAPI(FLIGetSerialString(dev, buff, BUFF_SIZE));
		printf("Serial Num:   %s\n", buff);

		DOFLIAPI(FLIGetPixelSize(dev, &d1, &d2));
		printf("Pixel Size:   %f x %f\n", d1, d2);

		DOFLIAPI(FLIGetArrayArea(dev, &tmp1, &tmp2, &tmp3, &tmp4));
		printf("Array Area:   (%ld, %ld)(%ld, %ld)\n", tmp1, tmp2, tmp3, tmp4);

		DOFLIAPI(FLIGetVisibleArea(dev, &tmp1, &tmp2, &tmp3, &tmp4));
		printf("Visible Area: (%ld, %ld)(%ld, %ld)\n", tmp1, tmp2, tmp3, tmp4);
		
	}

	if(dev != FLI_INVALID_DEVICE)
	{
		FLIClose(dev);
	}

	for(int i=0; i < numCams; i++)
	{
		free(listName[i]);
	}
}

void EnumerateCameras(flidomain_t enumDomain)
{
	numCams = 0;

	char file[MAX_PATH], name[MAX_PATH];
	long domain;

	FLICreateList(enumDomain);

	if(FLIListFirst(&domain, file, MAX_PATH, name, MAX_PATH) == 0)
	{
		do
		{
			listName[numCams] = (char*)malloc(strlen(file) + 1);
			strcpy(listName[numCams], file);

			listDomain[numCams] = domain;
			numCams++;
		}
		while((FLIListNext(&domain, file, MAX_PATH, name, MAX_PATH) == 0) && (numCams < MAX_DEVICES));
	}

	FLIDeleteList();
}
