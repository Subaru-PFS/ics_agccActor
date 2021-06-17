TARGET = test_centroid
LIBS = -lm -lcfitsio -L.
CC = gcc
CFLAGS = -Wall -fPIC

.PHONY: clean all default

default: $(TARGET)
all: default

SOURCES = valgrind_cent.c newCentroid.c fitswrappers.c
OBJECTS = $(SOURCES:.c=.o)
HEADERS = $(wildcard *.h)

%.o: %.c $(HEADERS)
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET): $(OBJECTS)
	$(CC) $(OBJECTS) -Wall $(LIBS) -o $@

clean:
	-rm -f *.o
