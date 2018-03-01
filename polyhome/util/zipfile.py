import os
import os.path
import zipfile

class ZFile(object):
    """zip包压缩和解压缩封装类"""
    def __init__(self, filename, mode='r', basedir=''):   
        self.filename = filename   
        self.mode = mode   
        if self.mode in ('w', 'a'):   
            self._zfile = zipfile.ZipFile(filename, self.mode, compression=zipfile.ZIP_DEFLATED)   
        else:   
            self._zfile = zipfile.ZipFile(filename, self.mode)   
        self.basedir = basedir   
        if not self.basedir:   
            self.basedir = os.path.dirname(filename)   
          
    def addfile(self, path, arcname=None):   
        path = path.replace('//', '/')   
        if not arcname:   
            if path.startswith(self.basedir):   
                arcname = path[len(self.basedir):]   
            else:   
                arcname = ''   
        self._zfile.write(path, arcname)   
              
    def addfiles(self, paths):   
        for path in paths:   
            if isinstance(path, tuple):   
                self.addfile(*path)   
            else:   
                self.addfile(path)   
              
    def close(self):   
        self._zfile.close()   
          
    def extract_to(self, path):   
        for p in self._zfile.namelist():   
            self.extract(p, path)  

    def set_password(self, pwd):
        arr = bytes(pwd, 'utf-8')
        self._zfile.setpassword(arr) 
              
    def extract(self, filename, path):   
        if not filename.endswith('/'):   
            f = os.path.join(path, filename)   
            dir = os.path.dirname(f)   
            if not os.path.exists(dir):   
                os.makedirs(dir) 
            with open(f, 'wb') as outfile:
                outfile.write(self._zfile.read(filename))