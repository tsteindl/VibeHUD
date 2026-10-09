import io, urllib.request, zipfile, pathlib
URL = 'https://files.waveshare.com/wiki/ESP32-S3-LCD-3.16/ESP32-S3-LCD-3.16-Demo.zip'
class Remote(io.RawIOBase):
    def __init__(self):
        self.pos = 0
        with urllib.request.urlopen(urllib.request.Request(URL, method='HEAD'), timeout=90) as response:
            self.size = int(response.headers['Content-Length'])
        self.cache = {}
    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos
    def tell(self): return self.pos
    def read(self, n=-1):
        n = min(n if n >= 0 else self.size, self.size-self.pos)
        if not n: return b''
        block = 4*1024*1024
        start = self.pos // block * block
        if start not in self.cache:
            req = urllib.request.Request(URL, headers={'Range': f'bytes={start}-{min(start+block,self.size)-1}'})
            with urllib.request.urlopen(req, timeout=90) as r:
                if r.status != 206: raise RuntimeError('Server ignored range request')
                self.cache[start] = r.read()
        data = self.cache[start][self.pos-start:self.pos-start+n]
        if len(data) < n:
            self.pos += len(data)
            return data + self.read(n-len(data))
        self.pos += len(data)
        return data
with zipfile.ZipFile(Remote()) as z:
    names = z.namelist()
    pathlib.Path('.tools/archive-list.txt').write_text('\n'.join(names), encoding='utf-8')
    targets = [n for n in names if '/Arduino/' in n and ('07_LVGL' in n or '/libraries/lvgl8/' in n)]
    print('Extracting',len(targets),'files',flush=True)
    for n in targets:
        if n.endswith('/'): continue
        z.extract(n,'.tools/vendor-extracted')
    print('Done',flush=True)
