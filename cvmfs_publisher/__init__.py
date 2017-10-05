"""Simple interface for publishing into CVMFS repository""" 

_in_txn = False
def start_txn(cvmfs_repo):
    global _in_txn
    if _in_txn:
        return 0
    if os.path.exists("/var/spool/cvmfs/%s/in_transaction.lock" % cvmfs_repo):
        result = os.system("cvmfs_server abort -f %s" % cvmfs_repo)
        if result:
            sys.stderr.write("Failed to abort lingering transaction (exit status %d)." % result)
            return 1
    result = os.system("cvmfs_server transaction %s" % cvmfs_repo)
    if result:
        print >> sys.stderr, "Transaction start failed (exit status %d); will not attempt update." % result
        return 1
    _in_txn = True

def publish_txn(cvmfs_repo):
    global _in_txn
    if _in_txn:
        _in_txn = False
        return os.system("cvmfs_server publish %s" % cvmfs_repo)
    return 0

def make_final_symlink(image_dir, singularity_rootfs, namespace, repo_name, repo_tag):
    """
    Create symlink: $ROOTFS/.images/$HASH -> $ROOTFS/$NAMESPACE/$IMAGE:$TAG
    """
    final_path = os.path.join(singularity_rootfs, namespace, "%s:%s" % (repo_name, repo_tag))
    final_dir = os.path.split(final_path)[0]
    if not os.path.exists(final_dir):
        retval = start_txn(singularity_rootfs)
        if retval:
            return retval
        try:
            os.makedirs(final_dir)
        except OSError as oe:
            if oe.errno != errno.EEXIST:
                raise
    if os.path.exists(final_path):
        # Final symlink exists and is already correct.
        link_value = os.readlink(final_path)
        if link_value == image_dir:
            print("Image is already latest revision.")
            return 0
        # Otherwise, clear the symlink; we will recreate.  Since CVMFS is transactional,
        # we don't care that an unlink / symlink is not atomic.
        retval = start_txn(singularity_rootfs)
        if retval:
            return retval
        os.unlink(final_path)
    retval = start_txn(singularity_rootfs)
    if retval:
        return retval
    os.symlink(image_dir, final_path)
    return 0

def publish_image(image_dir):
    if os.path.exists(image_dir):
        make_final_symlink(image_dir, singularity_rootfs, namespace, repo_name, repo_tag)
        return publish_txn()
    else:
        print("Image dir, %s, does not exist; triggering CVMFS mount." % image_dir)
        retval = start_txn(singularity_rootfs)
        if os.path.exists(image_dir):   # Same as above
            make_final_symlink(image_dir, singularity_rootfs, namespace, repo_name, repo_tag)
            return publish_txn()
        if retval:
            return retval
        try:
            os.makedirs(image_dir)
        except OSError as oe:
            if oe.errno != errno.EEXIST:
                raise
