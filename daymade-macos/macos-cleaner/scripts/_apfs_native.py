#!/usr/bin/env python3
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess

lib = c.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
def bind(name, args, result=c.c_int):
    f = getattr(lib, name); f.argtypes=args; f.restype=result; return f
copyfile = bind('copyfile', [c.c_char_p,c.c_char_p,c.c_void_p,c.c_uint32])
alloc = bind('copyfile_state_alloc', [], c.c_void_p)
state_get = bind('copyfile_state_get', [c.c_void_p,c.c_uint32,c.c_void_p])
free_state = bind('copyfile_state_free', [c.c_void_p])
listx = bind('listxattr', [c.c_char_p,c.c_void_p,c.c_size_t,c.c_int], c.c_ssize_t)
getx = bind('getxattr', [c.c_char_p,c.c_char_p,c.c_void_p,c.c_size_t,c.c_uint32,c.c_int], c.c_ssize_t)
remove_fd_xattr = bind('fremovexattr', [c.c_int,c.c_char_p,c.c_int])
set_fd_xattr = bind('fsetxattr', [c.c_int,c.c_char_p,c.c_void_p,c.c_size_t,c.c_uint32,c.c_int])
setx = bind('setxattr', [c.c_char_p,c.c_char_p,c.c_void_p,c.c_size_t,c.c_uint32,c.c_int])
acl_get = bind('acl_get_file', [c.c_char_p,c.c_int], c.c_void_p)
acl_text = bind('acl_to_text', [c.c_void_p,c.c_void_p], c.c_void_p)
acl_free = bind('acl_free', [c.c_void_p])
getattrlist = bind('getattrlist', [c.c_char_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_ulong])
fgetattrlist = bind('fgetattrlist', [c.c_int,c.c_void_p,c.c_void_p,c.c_size_t,c.c_uint])
setattrlist = bind('setattrlist', [c.c_char_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_ulong])
swap = bind('renamex_np', [c.c_char_p,c.c_char_p,c.c_uint])
chflags = bind('chflags', [c.c_char_p,c.c_uint32])

class Attr(c.Structure):
    _fields_=[('count',c.c_ushort),('reserved',c.c_ushort),('common',c.c_uint32),
              ('vol',c.c_uint32),('directory',c.c_uint32),('file',c.c_uint32),('fork',c.c_uint32)]
class Time(c.Structure):
    _fields_=[('seconds',c.c_long),('nanoseconds',c.c_long)]
def ok(result, label):
    if result < 0: raise OSError(c.get_errno(), label)
    return result
def xb(path): return os.fsencode(path)
def private_size_fd(fd):
    """Query one caller-owned, pinned regular-file descriptor without payload I/O.

    Missing/unsupported attributes and malformed replies raise rather than
    turning an unknown allocation into zero. The caller retains fd ownership.
    """
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise ValueError('private_size_fd requires a regular file')
    a=Attr(5,0,0x80000000,0,0,0,0x8)
    buf=c.create_string_buffer(64)
    c.set_errno(0)
    rc=fgetattrlist(fd,c.byref(a),buf,len(buf),0x20)
    if rc != 0:
        if rc == -1:
            raise OSError(c.get_errno(), 'fgetattrlist private size')
        raise RuntimeError(f'fgetattrlist private size returned {rc}')
    length=struct.unpack_from('<I',buf.raw,0)[0]
    if length != 32:
        raise ValueError(f'malformed private size reply length: {length}')
    returned=struct.unpack_from('<5I',buf.raw,4)
    if not returned[4] & 0x8:
        raise NotImplementedError('ATTR_CMNEXT_PRIVATESIZE was not returned')
    value=struct.unpack_from('<q',buf.raw,24)[0]
    if value < 0:
        raise ValueError(f'negative private size: {value}')
    return value
def private_size(path):
    """Open an explicit path without following any symlink, then query its fd.

    Call private_size_fd with the already pinned descriptor when another step
    established the selected file's identity before this call.
    """
    p=Path(os.fsdecode(path))
    if '..' in p.parts:
        raise ValueError('parent components are ambiguous with symlinks')
    parts=Path(os.path.abspath(p)).parts[1:]
    directory_fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    file_fd=None
    try:
        for part in parts[:-1]:
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                            dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd=next_fd
        file_fd=os.open(parts[-1] if parts else '.',
                        os.O_EVTONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory_fd)
        return private_size_fd(file_fd)
    finally:
        if file_fd is not None: os.close(file_fd)
        os.close(directory_fd)
def attrs(path):
    p=xb(path); n=ok(listx(p,None,0,1),'listxattr'); buf=c.create_string_buffer(n)
    if n: assert listx(p,buf,n,1)==n
    result={}
    for key in buf.raw.rstrip(b'\0').split(b'\0'):
        if not key: continue
        size=ok(getx(p,key,None,0,0,1),'getxattr'); data=c.create_string_buffer(size)
        assert getx(p,key,data,size,0,1)==size
        result[key.decode()]=data.raw.hex()
    return result
def acl(path):
    value=acl_get(xb(path),0x100)
    if not value: raise OSError(c.get_errno(),'acl_get_file')
    text=acl_text(value,None)
    if not text: raise OSError(c.get_errno(),'acl_to_text')
    try: return c.string_at(text).decode()
    finally: acl_free(text); acl_free(value)
def clone_info(path):
    a=Attr(5,0,0x80000000,0,0,0,0x100|0x200|0x1000); buf=c.create_string_buffer(256)
    ok(getattrlist(xb(path),c.byref(a),buf,256,0x20),'getattrlist clone attrs')
    returned=struct.unpack_from('<5I',buf.raw,4)
    assert returned[4] & 0x1300 == 0x1300, f'clone attributes unsupported: {returned}'
    clone_id,flags,refs=struct.unpack_from('<QQI',buf.raw,24)
    return {'clone_id':clone_id,'extended_flags':flags,'full_clone_refs':refs,
            'shares_all_blocks':bool(flags & 0x40)}
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def birthtime_exact(path):
    a=Attr(5,0,0x200,0,0,0,0); buf=c.create_string_buffer(64)
    ok(getattrlist(xb(path),c.byref(a),buf,64,0),'getattrlist birthtime')
    assert struct.unpack_from('<I',buf.raw,0)[0]==20
    return list(struct.unpack_from('<qq',buf.raw,4))
