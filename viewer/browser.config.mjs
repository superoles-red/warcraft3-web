import { defineConfig } from 'vite';
import { simFingerprint } from './tools/sim-fingerprint.mjs';

export default defineConfig({
  plugins: [{
    name: 'local-game-launch',
    transform(code, path) {
      if (path.endsWith('/src/render/frameCap.ts')) {
        const original = 'w.ow3replay?.maxFps;';
        if (!code.includes(original)) throw Error('Upstream frame limiter changed');
        const phone = '(matchMedia("(hover: none) and (pointer: coarse)").matches ? (new URLSearchParams(location.search).get("fps") === "60" ? 60 : 30) : undefined)';
        return code.replace(original, 'w.ow3replay?.maxFps ?? ' + phone + ';');
      }
      if (path.endsWith('/src/main.ts')) {
        const gate = 'import.meta.env.DEV && new URLSearchParams(location.search).has("dev")';
        if (!code.includes(gate)) throw Error('Upstream launch logic changed');
        return code.replace(gate, 'new URLSearchParams(location.search).has("local")');
      }
      if (path.endsWith('/src/vfs/loader.ts')) {
        // Present the original installation's object tables and art to the interpreter.
        // Upstream normally normalizes all clients to a common multiplayer balance patch.
        const first = code.indexOf('    const edits = await loadNormalization(build.version);');
        const last = code.indexOf('    const missing = profile.archives', first);
        const cascFirst = code.indexOf('    const build = version?.split(');
        const cascLast = code.indexOf('    // A 1.31 store carries', cascFirst);
        if ([first, last, cascFirst, cascLast].some(i => i < 0)) throw Error('Upstream data mount changed');
        return (code.slice(0, first) + '    const vfs = new EditionDataSource(mpq);\n' +
          code.slice(last, cascFirst) + '    const vfs = new EditionDataSource(casc);\n' +
          code.slice(cascLast)).replace('${downgrade ? "-downgraded" : ""}', '');
      }
      if (path.endsWith('/src/ui/voiceOptions.ts')) {
        return `
          export function bindVoiceRow(screen) {
            for (const name of ['VoiceControlRowLabel','VoiceDownloadButton','VoiceControlCheckBox','VoiceControlLabel']) {
              const frame = screen.frame(name); if (frame) frame.hidden = true;
            }
          }
          export function voiceDownloadPressed() {}
        `;
      }
      if (path.endsWith('/src/voice/model.ts')) {
        // The phone build omits the optional 250 MB speech model and its runtime.
        return `
          export const WHISPER_RATE = 16000;
          export const voiceModelInstalled = async () => false;
          export const voiceModelInstalledNow = () => false;
          export const onVoiceModelInstalled = () => () => {};
          export const installVoiceModel = async () => { throw Error("Voice control is unavailable in this build"); };
          export const preloadVoiceModel = () => {};
          export const transcribe = async () => "";
          export const forgetOldVoiceModels = () => {};
        `;
      }
    },
    enforce: 'pre',
  }],
  define: {
    __OW3_VERSION__: JSON.stringify('0.4.11'),
    __OW3_COMMIT__: JSON.stringify('e0530078'),
    __OW3_SIM_FINGERPRINT__: JSON.stringify(simFingerprint(process.cwd())),
    __OW3_PERF_MS__: 0,
    __OW3_PERF_SNAPSHOT_MS__: 0,
  },
  build: { target: 'es2022', outDir: '../dist', emptyOutDir: true, copyPublicDir: false },
});
