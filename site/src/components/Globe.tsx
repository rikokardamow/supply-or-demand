"use client";

import { useEffect, useRef } from "react";

import type { Point } from "@/lib/vessels";

/**
 * A slowly rotating globe carrying real vessel positions.
 *
 * Canvas and arithmetic — no WebGL, no globe library, no texture to download. An
 * orthographic projection of a sphere is six lines of trigonometry, and at this size the
 * difference between that and a 3D engine is invisible to a reader while the difference in
 * payload is about half a megabyte.
 *
 * **It draws only the near hemisphere.** A point is visible when its position vector still
 * points towards the viewer; everything on the far side is dropped rather than drawn faint,
 * because a sphere you can see through reads as a wireframe ball, not as the earth.
 *
 * The rotation is deliberately slow — a full turn takes two minutes. Fast enough to be
 * unmistakably live, slow enough to read as weight rather than as a spinner.
 *
 * Drawn for a white ground: a pale body, grey graticule, blue tankers. The geometry is
 * unchanged from the dark version; only the values are inverted.
 */

const TILT = (18 * Math.PI) / 180;
const SECONDS_PER_TURN = 120;
/**
 * Where the rotation begins.
 *
 * Coverage is densest between the Mediterranean and the Malacca Strait; starting at 0
 * puts the Atlantic in front of the reader and shows about eight points, which reads as
 * missing data rather than as clustered data. This is a composition choice about the first
 * frame only -- the globe still turns through every longitude.
 */
const START_SPIN = -1.05;

export function Globe({ points }: { points: Point[] }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const ctx = node.getContext("2d");
    if (!ctx) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let stopped = false;

    // Backing-store scaling. Without it the graticule renders as a soft grey smear on any
    // retina display, which is exactly the cheapness this design is trying to avoid.
    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const size = node!.clientWidth;
      node!.width = size * ratio;
      node!.height = size * ratio;
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0);
      return size;
    }

    let size = resize();
    const onResize = () => {
      size = resize();
    };
    window.addEventListener("resize", onResize);

    function draw(spin: number) {
      const c = ctx!;
      const half = size / 2;
      const r = half * 0.86;
      c.clearRect(0, 0, size, size);

      /** Orthographic projection. Returns null for anything on the far hemisphere. */
      const project = (latDeg: number, lonDeg: number) => {
        const lat = (latDeg * Math.PI) / 180;
        const lon = (lonDeg * Math.PI) / 180 + spin;
        const cosLat = Math.cos(lat);
        const z =
          Math.sin(TILT) * Math.sin(lat) +
          Math.cos(TILT) * cosLat * Math.cos(lon);
        if (z <= 0) return null;
        return {
          x: half + r * cosLat * Math.sin(lon),
          y:
            half -
            r *
              (Math.cos(TILT) * Math.sin(lat) -
                Math.sin(TILT) * cosLat * Math.cos(lon)),
          z,
        };
      };

      // The body. A radial fill offset towards the upper left gives the sphere a lit side
      // and a terminator, which is what stops an outline plus a grid reading as a flat
      // wireframe ball. Very dark -- it has to sit on black without becoming a grey disc.
      const body = c.createRadialGradient(
        half - r * 0.35,
        half - r * 0.35,
        r * 0.1,
        half,
        half,
        r,
      );
      body.addColorStop(0, "rgba(248,250,252,1)");
      body.addColorStop(0.7, "rgba(238,242,247,1)");
      body.addColorStop(1, "rgba(226,232,240,1)");
      c.beginPath();
      c.arc(half, half, r, 0, Math.PI * 2);
      c.fillStyle = body;
      c.fill();

      // The limb, picked out slightly brighter than the grid so the sphere has an edge.
      c.beginPath();
      c.arc(half, half, r, 0, Math.PI * 2);
      c.strokeStyle = "rgba(148,163,184,0.55)";
      c.lineWidth = 1;
      c.stroke();

      // Graticule. Enough to read as a globe turning; not so much that it becomes a net.
      c.strokeStyle = "rgba(148,163,184,0.32)";
      for (let lat = -60; lat <= 60; lat += 30) {
        c.beginPath();
        let started = false;
        for (let lon = -180; lon <= 180; lon += 3) {
          const p = project(lat, lon);
          if (!p) {
            started = false;
            continue;
          }
          if (started) c.lineTo(p.x, p.y);
          else {
            c.moveTo(p.x, p.y);
            started = true;
          }
        }
        c.stroke();
      }
      for (let lon = -180; lon < 180; lon += 30) {
        c.beginPath();
        let started = false;
        for (let lat = -90; lat <= 90; lat += 3) {
          const p = project(lat, lon);
          if (!p) {
            started = false;
            continue;
          }
          if (started) c.lineTo(p.x, p.y);
          else {
            c.moveTo(p.x, p.y);
            started = true;
          }
        }
        c.stroke();
      }

      // The vessels. Points nearer the centre of the disc are facing the viewer most
      // directly, so they carry the most light -- that gradient is what gives a flat
      // projection its curvature.
      for (const point of points) {
        const p = project(point.lat, point.lon);
        if (!p) continue;
        const alpha = 0.45 + 0.55 * p.z;

        // Tankers get a soft halo as well as a dot. Positions cluster hard into a few
        // chokepoints, so without it the dense areas render as one indistinct smudge and
        // the sparse ones as dust.
        if (point.tanker) {
          const glow = c.createRadialGradient(p.x, p.y, 0, p.x, p.y, 5);
          glow.addColorStop(0, `rgba(29,78,216,${alpha * 0.28})`);
          glow.addColorStop(1, "rgba(29,78,216,0)");
          c.beginPath();
          c.arc(p.x, p.y, 5, 0, Math.PI * 2);
          c.fillStyle = glow;
          c.fill();
        }

        c.beginPath();
        c.arc(p.x, p.y, point.tanker ? 2.1 : 1.6, 0, Math.PI * 2);
        // Blue for a tanker, mid-grey for everything else -- on white the unclassified
        // fleet has to darken rather than brighten to register.
        c.fillStyle = point.tanker
          ? `rgba(29,78,216,${alpha})`
          : `rgba(100,116,139,${alpha * 0.7})`;
        c.fill();
      }
    }

    if (still) {
      // A fixed, composed angle rather than a frozen arbitrary one.
      draw(START_SPIN);
    } else {
      const started = performance.now();
      const tick = (now: number) => {
        if (stopped) return;
        draw(
          START_SPIN +
            ((now - started) / 1000 / SECONDS_PER_TURN) * Math.PI * 2,
        );
        frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    }

    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
    };
  }, [points]);

  return (
    <canvas
      ref={canvas}
      role="img"
      aria-label={`A rotating globe showing ${points.length} vessel positions from the latest AIS capture`}
      style={{ width: "100%", aspectRatio: "1 / 1", display: "block" }}
    />
  );
}
