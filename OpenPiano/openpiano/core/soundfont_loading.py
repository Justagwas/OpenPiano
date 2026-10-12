from __future__ import annotations

import bisect
import ctypes
import hashlib
import io
import logging
import os
import struct
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openpiano.core.fluidsynth_loader import candidate_dll_dirs
from openpiano.core.file_reads import open_guarded_read

_VALIDATED_SOURCES = {
    '5b44bb34403ac67162716b249416d8c201040bdc5c7a4e0847836edc47b74514',
    '7038e5d3a9e618c3f3db87f274fc39b37bb5e89bd1a9a0278f9554e92c4bebe5',
    '905fc596bf93c069d3f4836e96c7702bb1cdcee93408e0727c1759e04b7a3060',
    '4ee21ac1d95c7091a70a5a5437d1f6dd8c8c16d6013e9e5a4cc0ef9dfd46489e',
    '2201c2486758715cbb0049df9aafd26030efbe9928861fee0b5b186893510af2',
    '25d3f493d81786629c2b3174677196384f89e9129fbaf8bd6cedd1c61b391cd6',
    'eb43e83208d3a7ba630f5c10dda9f8dee9579c45307aef852e0b09421bebe765',
    '904888b533b80b0ac4cdf29a67f4ef4b3750e80c527a3490ec3f683919e70356',
    '61e395a1755b9551c64bf78738e70f4e87354017feeb1dbc681a369389cd438a',
    'f46a12ccb9eb48b97f85d21d670d1051d546ff91d362e1bff7ab27bba2596ab6',
}
_LOGGER = logging.getLogger(__name__)
_MIN_PARALLEL_BYTES = 100*1024*1024
_COUNT = ctypes.c_int64
_LENGTH = ctypes.CFUNCTYPE(_COUNT, ctypes.c_void_p)
_SEEK = ctypes.CFUNCTYPE(_COUNT, _COUNT, ctypes.c_int, ctypes.c_void_p)
_READ = ctypes.CFUNCTYPE(_COUNT, ctypes.c_void_p, _COUNT, ctypes.c_void_p)
_TELL = ctypes.CFUNCTYPE(_COUNT, ctypes.c_void_p)
_SHDR = struct.Struct('<20sIIIIIBbHH')


class _Info(ctypes.Structure):
    _fields_ = [('frames', _COUNT), ('samplerate', ctypes.c_int), ('channels', ctypes.c_int),
                ('format', ctypes.c_int), ('sections', ctypes.c_int), ('seekable', ctypes.c_int)]


class _VirtualIO(ctypes.Structure):
    _fields_ = [('length', _LENGTH), ('seek', _SEEK), ('read', _READ),
                ('write', ctypes.c_void_p), ('tell', _TELL)]


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'')


def _metadata(path: Path):
    chunks = {}; sample_offset = sample_size = None
    with path.open('rb') as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'sfbk':
            raise ValueError('Invalid SoundFont header.')
        size = struct.unpack_from('<I', header, 4)[0] + 8
        if size != path.stat().st_size:
            raise ValueError('Invalid SoundFont length.')
        def scan(start, end, parent=b''):
            nonlocal sample_offset, sample_size
            position = start
            while position + 8 <= end:
                stream.seek(position); tag, length = struct.unpack('<4sI', stream.read(8))
                if position + 8 + length > end:
                    raise ValueError('Invalid SoundFont chunk length.')
                if tag == b'LIST':
                    if length < 4:
                        raise ValueError('Invalid SoundFont list.')
                    category = stream.read(4)
                    scan(position+12, position+8+length, category)
                elif parent in (b'INFO', b'pdta'):
                    if length > 16*1024*1024:
                        raise ValueError('Unexpected SoundFont metadata size.')
                    chunks[(parent, tag)] = stream.read(length)
                elif parent == b'sdta' and tag == b'smpl':
                    sample_offset, sample_size = position+8, length
                position += 8 + length + length % 2
            if position != end:
                raise ValueError('Invalid SoundFont padding.')
        scan(12, size)
    if sample_offset is None or sample_size is None or chunks[(b'INFO', b'ifil')][:2] != b'\x03\0':
        raise ValueError('Expected a compressed SF3 sample payload.')
    headers = list(_SHDR.iter_unpack(chunks[(b'pdta', b'shdr')]))
    return chunks, headers, sample_offset, sample_size


def _decoder(path: Path):
    dll = ctypes.CDLL(str(path))
    dll.sf_open_virtual.argtypes = [ctypes.POINTER(_VirtualIO), ctypes.c_int, ctypes.POINTER(_Info), ctypes.c_void_p]
    dll.sf_open_virtual.restype = ctypes.c_void_p
    dll.sf_command.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
    dll.sf_command.restype = ctypes.c_int
    dll.sf_readf_short.argtypes = [ctypes.c_void_p, ctypes.c_void_p, _COUNT]
    dll.sf_readf_short.restype = _COUNT
    dll.sf_close.argtypes = [ctypes.c_void_p]; dll.sf_close.restype = ctypes.c_int
    dll.sf_strerror.argtypes = [ctypes.c_void_p]; dll.sf_strerror.restype = ctypes.c_char_p
    return dll


def _decode(dll, encoded: bytes, rate: int) -> tuple[bytes, int]:
    stream = io.BytesIO(encoded); errors = []
    def seek(offset, whence, _):
        try:
            return stream.seek(offset, whence)
        except Exception as exc:
            errors.append(exc); return -1
    def read(pointer, count, _):
        try:
            block = stream.read(count); ctypes.memmove(pointer, block, len(block))
            return len(block)
        except Exception as exc:
            errors.append(exc); return 0
    callbacks = (_LENGTH(lambda _:len(encoded)), _SEEK(seek), _READ(read), _TELL(lambda _:stream.tell()))
    vio = _VirtualIO(callbacks[0], callbacks[1], callbacks[2], None, callbacks[3]); info = _Info()
    handle = dll.sf_open_virtual(ctypes.byref(vio), 0x10, ctypes.byref(info), None)
    if not handle:
        raise RuntimeError(dll.sf_strerror(None).decode('utf-8', errors='replace'))
    try:
        if info.channels != 1 or info.samplerate != rate or not 0 < info.frames <= rate*120:
            raise ValueError('Unexpected decoded sample format.')
        dll.sf_command(handle, 0x1014, None, 1)
        pcm = (ctypes.c_int16 * info.frames)()
        if dll.sf_readf_short(handle, pcm, info.frames) != info.frames or errors:
            raise RuntimeError('Could not decode complete SoundFont sample.')
        return bytes(pcm), info.frames
    finally:
        dll.sf_close(handle)


class _SampleFile:

    def __init__(self, source: Path, decoder_path: Path, stop_event=None):
        chunks, headers, self.offset, size = _metadata(source)
        self.source = source
        self.stop_event = stop_event
        self.decoder = _decoder(decoder_path)
        self.headers = headers[:-1]
        self.starts = []
        self.frames = []
        updated = []
        cursor = 0
        with source.open('rb') as stream:
            for h in self.headers:
                if not h[-1] & 16 or not 0 <= h[1] < h[2] <= size:
                    raise ValueError('Unsupported compressed sample layout.')
                length = h[2]-h[1]
                stream.seek(self.offset+h[1]+max(0,length-65536))
                tail = stream.read(min(length,65536))
                page = tail.rfind(b'OggS')
                if page < 0 or len(tail)-page < 27 or tail[page+4] != 0 or not tail[page+5] & 4:
                    raise ValueError('Missing final Ogg page.')
                frames = struct.unpack_from('<Q',tail,page+6)[0]
                if not 0 < frames <= h[5]*120 or not 0 <= h[3] < h[4] <= frames:
                    raise ValueError('Invalid decoded sample extent.')
                new = list(h)
                new[1:5] = [cursor,cursor+frames,cursor+h[3],cursor+h[4]]
                new[-1] &= ~16
                updated.append(tuple(new))
                self.starts.append(cursor*2)
                self.frames.append(frames)
                cursor += frames+46
        self.sample_bytes = cursor*2
        chunks[(b'pdta',b'shdr')] = b''.join(_SHDR.pack(*h) for h in updated+[headers[-1]])
        info = _chunk(b'LIST',b'INFO'+b''.join(_chunk(tag,data) for (parent,tag),data in chunks.items() if parent==b'INFO'))
        self.suffix = _chunk(b'LIST',b'pdta'+b''.join(_chunk(tag,data) for (parent,tag),data in chunks.items() if parent==b'pdta'))
        total = 12+len(info)+20+self.sample_bytes+len(self.suffix)
        if total >= 2**32:
            raise ValueError('Decoded SoundFont exceeds RIFF limits.')
        self.prefix = (b'RIFF'+struct.pack('<I',total-8)+b'sfbk'+info+
            b'LIST'+struct.pack('<I',self.sample_bytes+12)+b'sdtasmpl'+struct.pack('<I',self.sample_bytes))
        self.sample_position = len(self.prefix)
        self.total = total
        self.position = 0
        self.errors = []
        self.pool = ThreadPoolExecutor(max_workers=min(8,max(1,os.cpu_count() or 1)))
        self.order = iter(range(len(self.headers)))
        self.pending = {}
        self.current = None
        self.prefetch_started = False

    def check_cancel(self):
        if self.stop_event is not None and self.stop_event.is_set():
            raise InterruptedError('Recording export cancelled.')

    def _submit(self):
        if len(self.pending) >= 16:
            return
        index = next(self.order,None)
        if index is not None:
            self.pending[index] = self.pool.submit(self._decode_one,index)

    def _decode_one(self,index):
        self.check_cancel()
        h = self.headers[index]
        with self.source.open('rb') as stream:
            stream.seek(self.offset+h[1])
            encoded = stream.read(h[2]-h[1])
        pcm,frames = _decode(self.decoder,encoded,h[5])
        if frames != self.frames[index]:
            raise ValueError('Decoded sample length differs from final Ogg granule.')
        self.check_cancel()
        return pcm

    def read(self,pointer,count):
        self.check_cancel()
        if count < 0 or self.position+count > self.total:
            raise ValueError('Read outside virtual SoundFont.')
        position = self.position
        if position < self.sample_position:
            block = self.prefix[position:position+count]
        elif position >= self.sample_position+self.sample_bytes:
            start = position-self.sample_position-self.sample_bytes
            block = self.suffix[start:start+count]
        else:
            if not self.prefetch_started:
                self.prefetch_started = True
                for _ in range(16):
                    self._submit()
            start = position-self.sample_position
            index = bisect.bisect_right(self.starts,start)-1
            relative = start-self.starts[index]
            if relative+count > (self.frames[index]+46)*2:
                raise ValueError('Unexpected cross-sample native read.')
            if self.current is None or self.current[0] != index:
                future = self.pending.pop(index,None)
                pcm = future.result() if future is not None else self._decode_one(index)
                self.current = (index,pcm)
                self._submit()
            pcm = self.current[1]
            block = pcm[relative:relative+count]
            if len(block) < count:
                block += b'\0'*(count-len(block))
        if len(block) != count:
            raise ValueError('Unexpected native metadata read.')
        ctypes.memmove(pointer,block,count)
        self.position += count

    def close(self):
        self.pool.shutdown(wait=True,cancel_futures=True)
        self.pending.clear()
        self.current = None


_OPEN_FILE = ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_char_p)
_READ_FILE = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,_COUNT,ctypes.c_void_p)
_SEEK_FILE = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,_COUNT,ctypes.c_int)
_TELL_FILE = ctypes.CFUNCTYPE(_COUNT,ctypes.c_void_p)
_CLOSE_FILE = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p)


class _FileReader:
    def __init__(self, path):
        self.extent = None
        try:
            self.stream = open_guarded_read(path)
        except OSError:
            self.stream = open(path, 'rb')
        else:
            try:
                self.extent = os.fstat(self.stream.fileno()).st_size
            except BaseException:
                self.stream.close()
                raise

    def close(self):
        self.stream.close()


class _Loader:

    def __init__(self,synth,module):
        self.active = None
        self.token = None
        self.files = {}
        self.next_handle = 1
        self.lock = threading.Lock()
        self.callbacks = (_OPEN_FILE(self.open),_READ_FILE(self.read),_SEEK_FILE(self.seek),
                          _TELL_FILE(self.tell),_CLOSE_FILE(self.close))
        create = module.cfunc('new_fluid_defsfloader',ctypes.c_void_p,('settings',ctypes.c_void_p,1))
        setup = module.cfunc('fluid_sfloader_set_callbacks',ctypes.c_int,
            ('loader',ctypes.c_void_p,1),('open',_OPEN_FILE,1),('read',_READ_FILE,1),
            ('seek',_SEEK_FILE,1),('tell',_TELL_FILE,1),('close',_CLOSE_FILE,1))
        add = module.cfunc('fluid_synth_add_sfloader',None,
            ('synth',ctypes.c_void_p,1),('loader',ctypes.c_void_p,1))
        loader = create(synth.settings)
        if not loader:
            raise RuntimeError('Could not create native SoundFont loader.')
        if setup(loader,*self.callbacks) != 0:
            module.cfunc('delete_fluid_sfloader',None,('loader',ctypes.c_void_p,1))(loader)
            raise RuntimeError('Could not set native SoundFont callbacks.')
        add(synth.synth,loader)

    def open(self,filename):
        try:
            if filename==self.token and self.active is not None:
                stream = self.active
                stream.position = 0
            else:
                stream = _FileReader(os.fsdecode(filename))
            handle = self.next_handle
            self.next_handle += 1
            self.files[handle] = stream
            return handle
        except Exception:
            return None

    def read(self,pointer,count,handle):
        try:
            stream = self.files[handle]
            if isinstance(stream,_SampleFile):
                stream.read(pointer,count)
            else:
                extent = stream.extent if isinstance(stream, _FileReader) else None
                if isinstance(stream, _FileReader):
                    stream = stream.stream
                position = stream.tell()
                if count < 0 or position+count > (extent if extent is not None else os.fstat(stream.fileno()).st_size):
                    return -1
                data = stream.read(count)
                if len(data) != count:
                    return -1
                if count:
                    ctypes.memmove(pointer, data, count)
            return 0
        except Exception as exc:
            if self.active is not None:
                self.active.errors.append(exc)
            return -1

    def seek(self,handle,offset,origin):
        try:
            stream = self.files[handle]
            if isinstance(stream,_SampleFile):
                position = offset+(0 if origin==0 else stream.position if origin==1 else stream.total)
                if origin not in (0,1,2) or not 0 <= position <= stream.total:
                    return -1
                stream.position = position
            else:
                if isinstance(stream, _FileReader):
                    stream = stream.stream
                stream.seek(offset,origin)
            return 0
        except Exception:
            return -1

    def tell(self,handle):
        try:
            stream = self.files[handle]
            if isinstance(stream, _FileReader):
                stream = stream.stream
            return stream.position if isinstance(stream,_SampleFile) else stream.tell()
        except Exception:
            return -1

    def close(self,handle):
        try:
            stream = self.files.pop(handle)
            if not isinstance(stream,_SampleFile):
                stream.close()
            return 0
        except Exception:
            return -1

    def dispose(self):
        for stream in tuple(self.files.values()):
            stream.close()
        self.files.clear()
        self.active = None
        self.token = None
        self.callbacks = ()


def dispose_soundfont_loader(synth):
    loader = getattr(synth, '_openpiano_parallel_loader', None)
    if loader is not None:
        loader.dispose()
        synth._openpiano_parallel_loader = None


def _native_load(synth,path):
    try:
        return int(synth.sfload(str(path),reset_presets=False))
    except TypeError:
        try:
            return int(synth.sfload(str(path),False))
        except TypeError:
            return int(synth.sfload(str(path)))


def _prepare_parallel_loader(synth,module):
    if sys.platform != 'win32' or module is None:
        return None
    loader = getattr(synth,'_openpiano_parallel_loader',None)
    if loader is not None:
        return loader
    if module.cfunc('fluid_version_str',ctypes.c_char_p)() != b'2.5.2':
        return None
    count = module.cfunc('fluid_synth_sfcount',ctypes.c_int,('synth',ctypes.c_void_p,1))
    if count(synth.synth) != 0:
        return None
    loader = _Loader(synth,module)
    synth._openpiano_parallel_loader = loader
    return loader


def load_soundfont(synth,source: str,*,module=None,stop_event=None,capabilities=None) -> int:
    path = Path(source)
    if stop_event is not None and stop_event.is_set():
        raise InterruptedError('Recording export cancelled.')
    loader = None
    try:
        loader = _prepare_parallel_loader(synth,module)
    except Exception as exc:
        _LOGGER.warning('Parallel SoundFont loader setup unavailable; using native loader: %s',exc)
    if (loader is not None and path.suffix.lower()=='.sf3'
            and path.stat().st_size > _MIN_PARALLEL_BYTES
            and synth.get_setting('synth.dynamic-sample-loading') == 0):
        if capabilities is None:
            from openpiano.core.soundfont_capabilities import inspect_soundfont
            capabilities = inspect_soundfont(path, stop_event=stop_event)
        capabilities.validate_unchanged()
        eligible = capabilities.digest in _VALIDATED_SOURCES
        if eligible:
            state = None
            try:
                decoder = next(folder/'sndfile.dll' for folder in candidate_dll_dirs() if (folder/'sndfile.dll').is_file())
                with loader.lock:
                    source_stat = path.stat()
                    state = _SampleFile(path,decoder,stop_event)
                    loader.active = state
                    cache_key = (os.path.normcase(str(path.resolve())), capabilities.identity,
                                 capabilities.digest)
                    token = hashlib.sha256(repr(cache_key).encode('utf-8')).hexdigest()
                    loader.token = f'openpiano-memory:v1:{token}'.encode()
                    try:
                        sfid = _native_load(synth,loader.token.decode())
                        if state.errors:
                            if sfid >= 0:
                                synth.sfunload(sfid,False)
                            raise state.errors[0]
                        if sfid < 0:
                            raise RuntimeError('Native parallel SoundFont load failed.')
                        current_stat = path.stat()
                        if (source_stat.st_size,source_stat.st_mtime_ns) != (current_stat.st_size,current_stat.st_mtime_ns):
                            synth.sfunload(sfid,False)
                            raise RuntimeError('SoundFont changed during loading.')
                        try:
                            capabilities.validate_unchanged()
                        except Exception:
                            synth.sfunload(sfid, False)
                            raise
                        if stop_event is not None and stop_event.is_set():
                            synth.sfunload(sfid,False)
                            raise InterruptedError('Recording export cancelled.')
                        return sfid
                    finally:
                        loader.active = None
                        loader.token = None
                        state.close()
            except InterruptedError:
                raise
            except Exception as exc:
                if state is not None:
                    state.close()
                _LOGGER.warning('Parallel SoundFont loading unavailable; using native loader: %s',exc)
    sfid = _native_load(synth,path)
    if sfid < 0:
        raise RuntimeError(f'Unable to load SoundFont: {path}')
    if capabilities is not None:
        try:
            capabilities.validate_unchanged()
        except Exception:
            synth.sfunload(sfid, False)
            raise
    if stop_event is not None and stop_event.is_set():
        synth.sfunload(sfid, False)
        raise InterruptedError('SoundFont loading cancelled.')
    return sfid


