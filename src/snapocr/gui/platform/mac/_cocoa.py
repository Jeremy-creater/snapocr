"""ctypes declarations for Carbon, CoreGraphics, CoreFoundation and libobjc (M9 plan D11). No logic.

``send`` calls ``objc_msgSend`` cast to the exact signature of one method, which
is what arm64 needs (the call is not variadic there).
"""

from __future__ import annotations

import ctypes
import ctypes.util

vp = ctypes.c_void_p

carbon = ctypes.CDLL(ctypes.util.find_library("Carbon"))
cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
objc = ctypes.CDLL(ctypes.util.find_library("objc"))
ctypes.CDLL(ctypes.util.find_library("AppKit"))  # registers NSApplication / NSWindow with the runtime

# --- Carbon: global hotkeys (F23-2) ------------------------------------------------------
OSStatus = ctypes.c_int32
noErr = 0
eventNotHandledErr = -9874
kEventClassKeyboard = int.from_bytes(b"keyb", "big")
kEventHotKeyPressed = 5
kEventParamDirectObject = int.from_bytes(b"----", "big")
typeEventHotKeyID = int.from_bytes(b"hkid", "big")


class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


EventHandlerProcPtr = ctypes.CFUNCTYPE(OSStatus, vp, vp, vp)

carbon.GetApplicationEventTarget.restype = vp
carbon.GetApplicationEventTarget.argtypes = []
carbon.InstallEventHandler.restype = OSStatus
carbon.InstallEventHandler.argtypes = [vp, EventHandlerProcPtr, ctypes.c_uint32, ctypes.POINTER(EventTypeSpec), vp, ctypes.POINTER(vp)]
carbon.RemoveEventHandler.restype = OSStatus
carbon.RemoveEventHandler.argtypes = [vp]
carbon.RegisterEventHotKey.restype = OSStatus
carbon.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID, vp, ctypes.c_uint32, ctypes.POINTER(vp)]
carbon.UnregisterEventHotKey.restype = OSStatus
carbon.UnregisterEventHotKey.argtypes = [vp]
carbon.GetEventParameter.restype = OSStatus
carbon.GetEventParameter.argtypes = [vp, ctypes.c_uint32, ctypes.c_uint32, vp, ctypes.c_size_t, vp, vp]

# --- CoreGraphics: screens and capture (F23-3, F23-4) ------------------------------------
CGDirectDisplayID = ctypes.c_uint32


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
cg.CGPreflightScreenCaptureAccess.argtypes = []
cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
cg.CGRequestScreenCaptureAccess.argtypes = []
cg.CGGetActiveDisplayList.restype = ctypes.c_int32
cg.CGGetActiveDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(CGDirectDisplayID), ctypes.POINTER(ctypes.c_uint32)]
cg.CGDisplayBounds.restype = CGRect
cg.CGDisplayBounds.argtypes = [CGDirectDisplayID]
cg.CGDisplayCreateImage.restype = vp
cg.CGDisplayCreateImage.argtypes = [CGDirectDisplayID]
for _name in ("CGImageGetWidth", "CGImageGetHeight", "CGImageGetBytesPerRow", "CGImageGetBitsPerPixel", "CGImageGetBitmapInfo"):
    getattr(cg, _name).restype = ctypes.c_size_t
    getattr(cg, _name).argtypes = [vp]
cg.CGImageGetDataProvider.restype = vp
cg.CGImageGetDataProvider.argtypes = [vp]
cg.CGDataProviderCopyData.restype = vp
cg.CGDataProviderCopyData.argtypes = [vp]
cg.CGImageRelease.restype = None
cg.CGImageRelease.argtypes = [vp]

# --- CoreFoundation -------------------------------------------------------------------------
cf.CFDataGetBytePtr.restype = vp
cf.CFDataGetBytePtr.argtypes = [vp]
cf.CFDataGetLength.restype = ctypes.c_long
cf.CFDataGetLength.argtypes = [vp]
cf.CFRelease.restype = None
cf.CFRelease.argtypes = [vp]

# --- libobjc: NSApplication / NSWindow (F23-1, F23-4) ------------------------------------
objc.objc_getClass.restype = vp
objc.objc_getClass.argtypes = [ctypes.c_char_p]
objc.sel_registerName.restype = vp
objc.sel_registerName.argtypes = [ctypes.c_char_p]
_msg_send = ctypes.cast(objc.objc_msgSend, vp).value

NSApplicationActivationPolicyRegular = 0
NSApplicationActivationPolicyAccessory = 1
NSStatusWindowLevel = 25
NSScreenSaverWindowLevel = 1000
NSWindowCollectionBehaviorCanJoinAllSpaces = 1 << 0
NSWindowCollectionBehaviorFullScreenAuxiliary = 1 << 8


def send(receiver, selector: str, *args, restype=vp, argtypes=()):
    """``[receiver selector:args...]`` with the given C signature."""
    fn = ctypes.CFUNCTYPE(restype, vp, vp, *argtypes)(_msg_send)
    return fn(receiver, objc.sel_registerName(selector.encode()), *args)


def ns_class(name: str):
    return objc.objc_getClass(name.encode())


def ns_app():
    return send(ns_class("NSApplication"), "sharedApplication")
