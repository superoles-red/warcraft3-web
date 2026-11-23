#!/usr/bin/env python3
"""Compress classic PCM WAVs and campaign voices into a private overlay for the browser."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

MAGIC = b'W3AO'
HEADER = struct.Struct('<4sBBHIIIIII')


def wave_layout(source):
    if source[:4] != b'RIFF' or source[8:12] != b'WAVE':
        raise ValueError('expected RIFF WAVE')
    at = 12
    fields = None
    while at + 8 <= len(source):
        name, size = struct.unpack_from('<4sI', source, at)
        at += 8
        if at + size > len(source):
            break
        if name == b'fmt ' and size >= 16:
            fields = struct.unpack_from('<HHIIHH', source, at)
        if name == b'data' and fields:
            codec, channels, rate, _, align, bits = fields
            if codec != 1 or bits != 16 or channels not in (1, 2) or align != channels * 2 or size % align:
                raise ValueError('unsupported source PCM format')
            return channels, rate, size // align, source[:at], source[at + size:]
        at += size + size % 2
    raise ValueError('incomplete RIFF chunks')


def opus_packets(data):
    at = 0
    partial = bytearray()
    packets = []
    while at < len(data):
        if data[at:at+4] != b'OggS' or at + 27 > len(data):
            raise ValueError('invalid Ogg page')
        n = data[at+26]
        sizes = data[at+27:at+27+n]
        at += 27 + n
        for size in sizes:
            if at+size > len(data):
                raise ValueError('truncated Ogg segment')
            partial.extend(data[at:at+size])
            at += size
            if size < 255:
                packets.append(bytes(partial))
                partial.clear()
    if partial or len(packets) < 3 or packets[0][:8] != b'OpusHead' or packets[1][:8] != b'OpusTags':
        raise ValueError('incomplete Ogg Opus stream')
    return packets[0][9], struct.unpack_from('<H', packets[0], 10)[0], packets[2:]


def fast_ambient(path, common, channels, rate, frames, prefix, suffix):
    with tempfile.TemporaryDirectory() as temp:
        wave = Path(temp) / 'ambient.wav'
        subprocess.run(common + ['-map', '0:a:0', '-c:a', 'adpcm_ima_wav', '-block_size', '512',
                                  '-map_metadata', '-1', str(wave)], check=True)
        container = wave.read_bytes()
    at = 12
    while at + 8 <= len(container):
        name, size = struct.unpack_from('<4sI', container, at)
        at += 8
        if name == b'data' and at + size <= len(container):
            header = HEADER.pack(MAGIC, 2, channels, 0, len(prefix), len(suffix), frames, rate, 512, 0)
            return header + prefix + suffix + container[at:at+size]
        at += size + size % 2
    raise ValueError(f'Cannot read ADPCM data for {path}')


def encode(path, output, root, cached=None, cached_files=None):
    original = path.read_bytes()
    rel = path.relative_to(root)
    is_voice_mp3 = path.suffix == '.mp3'
    original_hash = hashlib.sha256(original).hexdigest()
    common = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-threads', '1', '-i', str(path)]
    layout = wave_layout(original) if not is_voice_mp3 else None
    is_ambient = layout and layout[2] > 15 * layout[1]
    previous = cached_files.get(rel.as_posix()) if cached_files else None
    if previous and previous['sourceSha256'] == original_hash:
        prior = cached / 'gamedata' / rel
        if previous['converted'] and prior.is_file():
            with prior.open('rb') as handle:
                version = handle.read(5)
            if version == MAGIC + bytes([2 if is_ambient else 1]):
                dest = output / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(prior, dest)
                except OSError:
                    import shutil
                    shutil.copyfile(prior, dest)
                return rel.as_posix(), len(original), dest.stat().st_size, original_hash, True
    if is_ambient:
        result = fast_ambient(path, common, *layout)
    else:
        with tempfile.TemporaryDirectory(dir=output.parent.parent) as workspace:
            pcm = Path(workspace) / 'decoded.wav'
            cmd = common + (['-map', '0:a:0', '-c:a', 'pcm_s16le', '-map_metadata', '-1', str(pcm)] if is_voice_mp3 else [])
            channels = wave_layout(original)[0] if not is_voice_mp3 else 1
            bitrate = '88k' if channels == 2 else ('44k' if is_voice_mp3 else '48k')
            cmd += ['-map', '0:a:0', '-c:a', 'libopus', '-b:a', bitrate, '-vbr', 'on', '-compression_level', '8',
                    '-frame_duration', '20', '-map_metadata', '-1', '-f', 'ogg', 'pipe:1']
            ogg = subprocess.check_output(cmd)
            ch, rate, frames, prefix, suffix = wave_layout(pcm.read_bytes() if is_voice_mp3 else original)
        enc_ch, preskip, packets = opus_packets(ogg)
        if enc_ch != ch or not frames:
            raise ValueError(f'Channel or frame count mismatch in {path}')
        header = HEADER.pack(MAGIC, 1, ch, 0, len(prefix), len(suffix), frames, rate, preskip, len(packets))
        result = b''.join([header, prefix, suffix, *(struct.pack('<H', len(p)) + p for p in packets)])
    # Preserve source bytes if the compact form fails to provide meaningful savings.
    changed = len(result) < 0.95 * len(original)
    if changed:
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result)
    return (rel.as_posix(), len(original), len(result) if changed else len(original), original_hash, changed)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    local = Path(__file__).resolve().parents[1] / 'local'
    p.add_argument('--source', type=Path, default=local / 'gamedata')
    p.add_argument('--output', type=Path, default=local / 'audio-compact')
    p.add_argument('--reuse', type=Path, help='Reuse matching encoded files from a prior completed overlay')
    p.add_argument('--jobs', type=int, default=4)
    args = p.parse_args()
    root = args.source.resolve()
    output = args.output.resolve()
    if output.exists() or not (root / 'ui/framedef/framedef.toc').is_file() or args.jobs < 1:
        p.error('use a prepared game tree, a new output directory and at least one encoding worker')
    files = sorted(set(root.rglob('*.wav')) | set((root / 'sound/dialogue').rglob('*.mp3')))
    if not files:
        p.error('no game audio found')
    reuse = args.reuse.resolve() if args.reuse else None
    cached_files = json.loads((reuse / 'audio-report.json').read_text())['files'] if reuse else {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.audio-build-', dir=output.parent) as temp:
        stage = Path(temp) / 'overlay'
        data = stage / 'gamedata'
        data.mkdir(parents=True)
        def run(path):
            return encode(path, data, root, reuse, cached_files)
        records = {}
        totals = Counter()
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for i, (rel, before, after, digest, changed) in enumerate(pool.map(run, files), 1):
                records[rel] = {'sourceSha256': digest, 'sourceBytes': before, 'compactBytes': after, 'converted': changed}
                totals.update(source=before, compact=after, converted=int(changed))
                if i % 400 == 0:
                    print(f'{i}/{len(files)} files', flush=True)
        manifest = dict(format='w3ao1', totals=totals, files=records)
        (stage / 'audio-report.json').write_text(json.dumps(manifest, indent=2) + '\n')
        stage.rename(output)
        print(json.dumps(totals))


if __name__ == '__main__':
    main()
