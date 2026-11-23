// Validate the whole compact overlay with the same synchronous decoder as the browser.
import fs from 'node:fs';
import path from 'node:path';
import {prepareGameAudio} from '../engine/audio-runtime.mjs';
const local = path.resolve(process.argv[2] || 'local');
const overlay = path.join(local, 'audio-compact'), report = JSON.parse(fs.readFileSync(path.join(overlay, 'audio-report.json')));
const decode = await prepareGameAudio();
const counts = {opus:0, ima:0}, sizes = {opus:0, ima:0};
let frames = 0, slowest = {ms:0};
for (const [name, entry] of Object.entries(report.files)) {
  if (!entry.converted) continue;
  const bytes = fs.readFileSync(path.join(overlay, 'gamedata', name));
  if (bytes.length !== entry.compactBytes) throw Error('Compressed size mismatch: ' + name);
  const t = performance.now(), pcm = decode(bytes), elapsed = performance.now() - t;
  if (pcm[0] !== 82 || pcm[1] !== 73 || pcm[2] !== 70 || pcm[3] !== 70) throw Error('Missing RIFF: ' + name);
  const length = bytes.readUInt32LE(16), channels = bytes[5], prefix = bytes.readUInt32LE(8), suffix = bytes.readUInt32LE(12);
  if (pcm.length !== prefix + suffix + length * channels * 2) throw Error('Incorrect frame count: ' + name);
  if (name.endsWith('.wav')) {
    const original = fs.readFileSync(path.join(local,'gamedata',name)), result = Buffer.from(pcm.buffer,pcm.byteOffset,pcm.byteLength);
    if (original.length !== result.length || !original.subarray(0,prefix).equals(result.subarray(0,prefix)) ||
        !original.subarray(result.length-suffix).equals(result.subarray(result.length-suffix))) throw Error('Source timing/header mismatch: ' + name);
  }
  const mode = bytes[4] === 2 ? 'ima' : 'opus';
  counts[mode]++; sizes[mode] += bytes.length; frames += length;
  if (elapsed > slowest.ms) slowest = {name,ms:Math.round(elapsed)};
}
console.log(JSON.stringify({counts,compactBytes:sizes,frames,slowest},null,2));
