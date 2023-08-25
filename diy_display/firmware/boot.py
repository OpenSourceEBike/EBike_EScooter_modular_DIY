import storage
storage.disable_usb_drive()
storage.remount("/", readonly=False)
storage.enable_usb_drive()
