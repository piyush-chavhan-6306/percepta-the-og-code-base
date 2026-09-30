import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Geometry of an `object-contain` image: where the picture actually is.
 *
 * `getBoundingClientRect()` on an `<img class="w-full h-full object-contain">`
 * returns the *element* box, which is not where the picture is drawn. With
 * `object-contain` the frame is scaled to fit and centred, so any aspect-ratio
 * mismatch leaves letterbox bars inside that rect. Converting a click with the
 * element rect therefore lands off-target, and an overlay stretched across the
 * element rect draws in the wrong place.
 *
 * This hook reports the real picture box plus the frame's intrinsic size, so
 * clicks and overlays share one coordinate space: source-frame pixels.
 */
export interface DisplayedImageRect {
  /** Intrinsic frame size in pixels; 0 until the first frame decodes. */
  frameWidth: number;
  frameHeight: number;
  /** Element bounding rect relative to viewport. */
  elementLeft: number;
  elementTop: number;
  /** The drawn picture box, in CSS pixels relative to the image element. */
  offsetX: number;
  offsetY: number;
  displayWidth: number;
  displayHeight: number;
  /** displayWidth / frameWidth. */
  scale: number;
  /** True once a frame has decoded and the box has been measured. */
  ready: boolean;
}

const EMPTY: DisplayedImageRect = {
  frameWidth: 0,
  frameHeight: 0,
  elementLeft: 0,
  elementTop: 0,
  offsetX: 0,
  offsetY: 0,
  displayWidth: 0,
  displayHeight: 0,
  scale: 1,
  ready: false,
};

function computeRect(img: HTMLImageElement | null): DisplayedImageRect {
  if (!img) return EMPTY;

  const frameWidth = img.naturalWidth;
  const frameHeight = img.naturalHeight;
  const rect = img.getBoundingClientRect();

  // naturalWidth is 0 while a frame is still decoding, and stays 0 for a broken
  // stream. Guessing a size here is what produces silently-misplaced points, so
  // report not-ready instead and let the caller ignore input until it is.
  if (!frameWidth || !frameHeight || !rect.width || !rect.height) return EMPTY;

  const scale = Math.min(rect.width / frameWidth, rect.height / frameHeight);
  const displayWidth = frameWidth * scale;
  const displayHeight = frameHeight * scale;

  return {
    frameWidth,
    frameHeight,
    elementLeft: rect.left,
    elementTop: rect.top,
    // object-contain centres the picture in both axes (object-position default).
    offsetX: (rect.width - displayWidth) / 2,
    offsetY: (rect.height - displayHeight) / 2,
    displayWidth,
    displayHeight,
    scale,
    ready: true,
  };
}

export function useDisplayedImageRect(
  imgRef: React.RefObject<HTMLImageElement | null>,
): { rect: DisplayedImageRect; remeasure: () => void } {
  const [rect, setRect] = useState<DisplayedImageRect>(EMPTY);
  const rafRef = useRef<number | null>(null);

  const remeasure = useCallback(() => {
    // Measure on the next frame: a load event can fire before layout settles,
    // and a ResizeObserver can fire several times in one tick.
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const next = computeRect(imgRef.current);
      setRect((prev) =>
        prev.frameWidth === next.frameWidth &&
        prev.frameHeight === next.frameHeight &&
        prev.elementLeft === next.elementLeft &&
        prev.elementTop === next.elementTop &&
        prev.displayWidth === next.displayWidth &&
        prev.displayHeight === next.displayHeight &&
        prev.ready === next.ready
          ? prev
          : next,
      );
    });
  }, [imgRef]);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;

    remeasure();

    // A cached or already-complete image never fires `load`.
    if (img.complete) remeasure();

    const observer = new ResizeObserver(remeasure);
    observer.observe(img);
    window.addEventListener("resize", remeasure);

    // Polling fallback: MJPEG streams may not fire onLoad until closed.
    // If the image gets a naturalWidth but ResizeObserver doesn't catch it,
    // we need to poll until we get a valid size.
    const pollInterval = setInterval(() => {
      if (img.naturalWidth > 0) {
        remeasure();
      }
    }, 500);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", remeasure);
      clearInterval(pollInterval);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [imgRef, remeasure]);

  return { rect, remeasure };
}

export function clickToFrameCoords(
  clientXOrEvent: number | { clientX: number; clientY: number; currentTarget?: any },
  clientYOrRect: number | DisplayedImageRect,
  maybeRect?: DisplayedImageRect,
): [number, number] | null {
  let clientX = 0;
  let clientY = 0;
  let rect: DisplayedImageRect;

  if (typeof clientXOrEvent === "number") {
    clientX = clientXOrEvent;
    clientY = clientYOrRect as number;
    rect = maybeRect!;
  } else {
    clientX = clientXOrEvent.clientX;
    clientY = clientXOrEvent.clientY;
    rect = clientYOrRect as DisplayedImageRect;
  }

  if (!rect || !rect.ready) return null;

  // Subtract element screen offset (bounding client rect) and internal letterbox offset
  const elLeft = rect.elementLeft ?? 0;
  const elTop = rect.elementTop ?? 0;
  const x = clientX - elLeft - rect.offsetX;
  const y = clientY - elTop - rect.offsetY;

  if (x < 0 || y < 0 || x > rect.displayWidth || y > rect.displayHeight) return null;

  return [
    Math.round(Math.min(rect.frameWidth, Math.max(0, x / rect.scale))),
    Math.round(Math.min(rect.frameHeight, Math.max(0, y / rect.scale))),
  ];
}
