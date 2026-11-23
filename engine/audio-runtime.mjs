// Decode compact, locally prepared audio to the classic mixer's input format.
// The original RIFF header and suffix preserve duration, cue points, and loop metadata.
import {decodeIma} from './audio-ima.mjs';
import createLibopus from '../lib/libopus-wasm/generated/libopus.generated.mjs';

const clockRate = 48000;
const packetSamples = 960; // the pack encoder uses 20 ms Opus frames
const headerBytes = 32;
const maxWaveSize = 128 * 1024 * 1024;

export async function prepareGameAudio() {
  const lib = await createLibopus();
  return function decodeGameAudio(bytes) {
    if (bytes.length < 4 || bytes[0] !== 87 || bytes[1] !== 51 || bytes[2] !== 65 || bytes[3] !== 79) return bytes;
    const h = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const channels = bytes[5], version = bytes[4];
    if (bytes.length < headerBytes || (version !== 1 && version !== 2) || ![1, 2].includes(channels)) {
      throw Error('Неподдерживаемый заголовок игрового звука.');
    }
    const prefix = h.getUint32(8, true), suffix = h.getUint32(12, true);
    const frames = h.getUint32(16, true), rate = h.getUint32(20, true);
    const skip = h.getUint32(24, true), packets = h.getUint32(28, true);
    const dataSize = frames * channels * 2, size = prefix + dataSize + suffix;
    let offset = headerBytes + prefix + suffix;
    if (prefix < 44 || prefix % 2 || offset > bytes.length || size > maxWaveSize || !frames ||
        !rate || rate > clockRate || (version === 1 && (!packets || packets > (bytes.length - offset) / 3)) ||
        h.getUint32(headerBytes, false) !== 0x52494646 ||
        h.getUint32(headerBytes + prefix - 8, false) !== 0x64617461 ||
        h.getUint32(headerBytes + prefix - 4, true) !== dataSize) {
      throw Error('Некорректный размер игрового звука.');
    }
    const out = new Uint8Array(size);
    out.set(bytes.subarray(headerBytes, headerBytes + prefix));
    out.set(bytes.subarray(headerBytes + prefix, offset), prefix + dataSize);
    const target = new Int16Array(out.buffer, prefix, frames * channels);
    if (version === 2) {
      decodeIma(bytes.subarray(offset), target, frames, channels, skip);
      return out;
    }
    const error = lib._malloc(4);
    const src = lib._malloc(1275); // RFC 6716 maximum bytes for a 20 ms single-frame packet
    const pcm = lib._malloc((packetSamples + 1) * channels * 2);
    let decoder = 0, emitted = 0, clock = 0;
    try {
      if (!error || !src || !pcm) throw Error('Недостаточно памяти для игрового звука.');
      decoder = lib._oc_create_decoder(clockRate, channels, error);
      if (!decoder || lib.HEAP32[error >> 2] !== 0) throw Error('Не удалось открыть декодер Opus.');
      for (let packet = 0; packet < packets; packet++) {
        if (offset + 2 > bytes.length) throw Error('Неполный пакет игрового звука.');
        const length = h.getUint16(offset, true);
        offset += 2;
        if (!length || length > 1275 || offset + length > bytes.length) throw Error('Повреждён пакет Opus.');
        lib.HEAPU8.set(bytes.subarray(offset, offset + length), src);
        offset += length;
        // Keep the last frame in the first slots for interpolation across packet boundaries.
        const decoded = lib._oc_decode(decoder, src, length, pcm + 2 * channels, packetSamples, 0);
        if (decoded !== packetSamples) throw Error('Некорректная длительность пакета Opus.');
        const samples = lib.HEAP16.subarray(pcm >> 1, (pcm >> 1) + (decoded + 1) * channels);
        const last = clock + decoded - 1;
        const final = packet + 1 === packets;
        const stop = final ? last + 1 : last;
        while (emitted < frames) {
          const position = emitted * clockRate / rate + skip;
          if (position >= stop) break;
          const left = Math.floor(position);
          const fraction = position - left;
          const a = (left - clock + 1) * channels;
          const b = left === last ? a : a + channels;
          for (let c = 0; c < channels; c++) {
            target[emitted * channels + c] = Math.round(samples[a+c] + fraction * (samples[b+c] - samples[a+c]));
          }
          emitted++;
        }
        samples.copyWithin(0, decoded * channels, (decoded + 1) * channels);
        clock += decoded;
      }
      if (emitted !== frames || offset !== bytes.length) throw Error('Игровой звук прочитан не полностью.');
      return out;
    } finally {
      if (decoder) lib._oc_destroy_decoder(decoder);
      lib._free(pcm); lib._free(src); lib._free(error);
    }
  };
}
