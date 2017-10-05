"""Download and mount Docker images using overlayfs on Linux"""

import os
import ctypes
import docker
import tempfile
import collections

MountPoint = collections.namedtuple('MountPoint', 'mount_point, dir_to_cleanup')

def mount(source, target, fs, options=""):
  ret = ctypes.CDLL("libc.so.6", use_errno=True).mount(source, target, fs, 0, options)
  if ret < 0:
    errno = ctypes.get_errno()
    raise RuntimeError("Error mounting {} ({}) on {} with options '{}': {}".
     format(source, fs, target, options, os.strerror(errno)))

def umount(target):
    ret = ctypes.CDLL("libc.so.6", use_errno=True).umount(target)
    if ret < 0:
        errno = ctypes.get_errno()
        raise RuntimeError("Error unmounting {}: {}".format(target, os.strerror(errno)))

def find_overlay_link_from_diff(diff_dir):
    if os.path.exists(diff_dir):
        link_file = open(diff_dir.replace("diff", "link"),"r")
        link_name = link_file.readline()
        return ("/var/lib/docker/overlay2/l/" + link_name)
    else:
        return None

def get_image(image=None, username=None, token=None, registry=None):
    client = docker.from_env()
    
    if username is not None and token is not None:
        client.login(username=args.username, password=args.token,
                registry=args.registry)
    
    return client.images.pull(image)

# in images that I have seen, there are 0-N lower dirs and exactly 1 upper dir
# with 0 lower dirs being common for "root" images like centos.
#
# The goal is to find the short link for each directory (this avoids page size
# limitations on arguments to mount) and recombine them into a single list.
# The link corresponding to upperdir will come first followed by the links for
# the lowerdirs in their original order. We will remount them as a single
# overlay of multiple lowerdirs so that the result is read-only. In the instance
# that there is 1 upper dir and 0 lower dirs, we will create a fake empty
# directory for the lowest layer. 
def overlay_mount(image):
    image_data = image.attrs["GraphDriver"]["Data"]
    lower_dirs = image_data["LowerDir"].split(":") if "LowerDir" in image_data else []
    upper_dirs = image_data["UpperDir"].split(":") if "UpperDir" in image_data else []
    combined_dirs = upper_dirs + lower_dirs
    
    combined_links = ":".join(map(find_overlay_link_from_diff, combined_dirs))
    
    tmp_empty_dir = None
    if len(combined_dirs) == 1:
        tmp_empty_dir = tempfile.mkdtemp(prefix="empty-dir-", dir="/tmp")
        combined_links += ":" + tmp_empty_dir
    
    mount_point = tempfile.mkdtemp(prefix="singularity-image-", dir="/tmp").encode()
    mount(b"overlay", mount_point, b"overlay",
            b"lowerdir=" + combined_links.encode())
    return MountPoint(mount_point=mount_point, dir_to_cleanup=tmp_empty_dir)

def overlay_cleanup(mount_point, dir_to_cleanup):
    umount(mount_point)
    os.rmdir(mount_point)
    if dir_to_cleanup is not None:
        os.rmdir(dir_to_cleanup)
