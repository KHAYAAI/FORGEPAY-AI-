/**
 * Real-time audio waveform visualizer using Web Audio API AnalyserNode.
 * Renders as an animated SVG — no canvas, no dependencies.
 */

import { useEffect, useRef } from "react";

interface AudioVisualizerProps {
  isListening: boolean;
  isSpeaking: boolean;
}

const BAR_COUNT = 32;
const MIN_BAR_HEIGHT = 4;
const MAX_BAR_HEIGHT = 48;

export function AudioVisualizer({ isListening, isSpeaking }: AudioVisualizerProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const animFrameRef = useRef<number>(0);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (!isListening) {
      cancelAnimationFrame(animFrameRef.current);
      resetBars();
      return;
    }

    (async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);
      analyserRef.current = analyser;

      const data = new Uint8Array(analyser.frequencyBinCount);
      const draw = () => {
        analyser.getByteFrequencyData(data);
        updateBars(data);
        animFrameRef.current = requestAnimationFrame(draw);
      };
      draw();
    })();

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [isListening]);

  function updateBars(data: Uint8Array) {
    const svg = svgRef.current;
    if (!svg) return;
    const bars = svg.querySelectorAll<SVGRectElement>("[data-bar]");
    const step = Math.floor(data.length / BAR_COUNT);
    bars.forEach((bar, i) => {
      const value = data[i * step] ?? 0;
      const height = MIN_BAR_HEIGHT + (value / 255) * (MAX_BAR_HEIGHT - MIN_BAR_HEIGHT);
      bar.setAttribute("height", String(height));
      bar.setAttribute("y", String((MAX_BAR_HEIGHT - height) / 2));
    });
  }

  function resetBars() {
    const svg = svgRef.current;
    if (!svg) return;
    svg.querySelectorAll<SVGRectElement>("[data-bar]").forEach((bar) => {
      bar.setAttribute("height", String(MIN_BAR_HEIGHT));
      bar.setAttribute("y", String((MAX_BAR_HEIGHT - MIN_BAR_HEIGHT) / 2));
    });
  }

  const barWidth = 4;
  const gap = 3;
  const totalWidth = BAR_COUNT * (barWidth + gap) - gap;

  const color = isSpeaking ? "#6366f1" : isListening ? "#10b981" : "#d1d5db";

  return (
    <svg
      ref={svgRef}
      width={totalWidth}
      height={MAX_BAR_HEIGHT}
      viewBox={`0 0 ${totalWidth} ${MAX_BAR_HEIGHT}`}
      className="transition-colors duration-300"
      aria-hidden="true"
    >
      {Array.from({ length: BAR_COUNT }, (_, i) => (
        <rect
          key={i}
          data-bar
          x={i * (barWidth + gap)}
          y={(MAX_BAR_HEIGHT - MIN_BAR_HEIGHT) / 2}
          width={barWidth}
          height={MIN_BAR_HEIGHT}
          rx={2}
          fill={color}
          style={{ transition: "fill 0.3s" }}
        />
      ))}
    </svg>
  );
}
