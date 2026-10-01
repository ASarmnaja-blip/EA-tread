"""Transcribe the operator's six setup videos (Thai narration) with faster-whisper on the CPU. Writes data/videos/clip<i>.json (segments with
start / end / text) and clip<i>.txt (one timestamped line per segment). Usage: python research/videos/transcribe.py [model]"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(r"C:\Users\66985\.claude\uploads\d02313cd-7d94-4111-9dc9-8d78c8e88775")
OUT = ROOT / "data" / "videos"; OUT.mkdir(parents=True, exist_ok=True)
FILES = ["5f3a351a-a6e757bb3f40e9b1a485c7f0916ff0cc.mp4", "39f9e5ea-fcaa37d24793cbeb6501ea8b7e4e4d94.mp4", "c5e557ea-b4748946c42f9a5562071342f4b8defd.mp4",
         "58ceb02e-da8db8053acc8b0f2ac7d58cfebc97db.mp4", "7fbb7ebd-c43ba7b2a7d958d58b7fef7247a05ad4.mp4", "3c9e278d-58b7d8e04a4c7a00f771755d9993d358.mp4"]
ORDER = [2, 1, 0, 5, 4, 3]                       # shortest first
PROMPT = ("เทรดทอง XAUUSD กราฟ แท่งเทียน ไส้เทียน HH HL LH LL โครงสร้าง แนวรับ แนวต้าน เบรค รีเทส ย่อ เด้ง กลับตัว ไทม์เฟรม M5 M15 H1 H4 "
          "Stop Loss Take Profit ออเดอร์ Buy Sell คอนเฟิร์ม โซน Liquidity Order Block Supply Demand เทรนด์ ไซด์เวย์")


def load_audio(path, sr=16000):
    """Mono 16 kHz float32 PCM decoded with PyAV directly (faster-whisper 1.2.1 passes an argument PyAV 19 no longer accepts)."""
    import av
    import numpy as np
    chunks = []
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        res = av.AudioResampler(format="s16", layout="mono", rate=sr)
        for frame in container.decode(stream):
            for f in res.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
        for f in res.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def main():
    from faster_whisper import WhisperModel
    name = sys.argv[1] if len(sys.argv) > 1 else "medium"
    t0 = time.time()
    model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=6)
    print(f"model {name} loaded ({time.time() - t0:.0f}s)", flush=True)
    for i in ORDER:
        if (OUT / f"clip{i}.json").exists():
            continue
        f = SRC / FILES[i]
        t1 = time.time()
        segs, info = model.transcribe(load_audio(f), language="th", beam_size=1, temperature=0.0, vad_filter=True, condition_on_previous_text=False)   # a prompt made the model copy it (clip 1)
        rows = []
        with open(OUT / f"clip{i}{'' if name == 'medium' else '_' + name}.txt", "w", encoding="utf-8") as fh:
            for s in segs:
                rows.append(dict(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip()))
                fh.write(f"[{s.start:7.1f}-{s.end:7.1f}] {s.text.strip()}\n")
                fh.flush()
        (OUT / f"clip{i}{'' if name == 'medium' else '_' + name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"clip {i}: {info.duration:.0f}s audio, {len(rows)} segments ({time.time() - t1:.0f}s)", flush=True)
    print(f"all done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
