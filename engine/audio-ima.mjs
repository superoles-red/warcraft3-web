// Microsoft IMA WAV uses one predictor per channel and groups of four bytes
// (eight following samples) per channel, in least-significant nibble order.
const steps = [7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767];
const adjustment = [-1,-1,-1,-1,2,4,6,8];
const difference = new Int32Array(89 * 16);
const next = new Int32Array(89 * 16);
for (let state = 0; state < steps.length; state++) {
  for (let nibble = 0; nibble < 16; nibble++) {
    const step = steps[state], i = state * 16 + nibble;
    const magnitude = (step >> 3) + (nibble & 1 ? step >> 2 : 0) + (nibble & 2 ? step >> 1 : 0) + (nibble & 4 ? step : 0);
    difference[i] = nibble & 8 ? -magnitude : magnitude;
    next[i] = 16 * Math.max(0, Math.min(88, state + adjustment[nibble & 7]));
  }
}

export function decodeIma(bytes, target, frameCount, channels, blockSize) {
  if (blockSize !== 512 || bytes.length % blockSize) throw Error('Некорректные блоки фонового звука.');
  const blockFrames = 1 + 2 * (blockSize - channels * 4) / channels;
  if (Math.ceil(frameCount / blockFrames) !== bytes.length / blockSize) throw Error('Некорректная длительность фонового звука.');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let block = 0, base = 0; block < bytes.length; block += blockSize, base += blockFrames) {
    const stop = Math.min(blockFrames, frameCount - base);
    for (let channel = 0; channel < channels; channel++) {
      let sample = view.getInt16(block + 4 * channel, true), state = bytes[block + 4 * channel + 2] * 16;
      if (state >= difference.length) throw Error('Некорректный предиктор фонового звука.');
      let frame = 0;
      target[base * channels + channel] = sample;
      for (let group = block + channels * 4 + channel * 4; frame + 1 < stop; group += channels * 4) {
        for (let j = 0; j < 4 && frame + 1 < stop; j++) {
          const packed = bytes[group + j];
          for (let shift = 0; shift < 8 && frame + 1 < stop; shift += 4) {
            const index = state + ((packed >> shift) & 15);
            sample = Math.min(32767, Math.max(-32768, sample + difference[index]));
            state = next[index];
            target[(base + ++frame) * channels + channel] = sample;
          }
        }
      }
    }
  }
}
