# FLI Camera Hardware Setup

To use the FLI USB cameras, the USB driver and library must be installed.

## Library

The FLI library source is in `c/libfli-1.999.1-180223/`. Build it with:

```bash
cd c/libfli-1.999.1-180223
make
```

## New Computer Setup

Add the `pfs` and `pfs-data` users to the `plugdev` group in `/etc/group`:

```
plugdev:x:46:pfs, pfs-data
```

Create a udev rule at `/etc/udev/rules.d/99-agc.rules` so the cameras are accessible without root:

```
SUBSYSTEM=="usb", ACTION=="add", ATTRS{idVendor}=="0f18", ATTRS{idProduct}=="000a", GROUP="plugdev"
```
