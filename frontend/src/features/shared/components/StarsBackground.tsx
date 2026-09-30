import React, { useRef, useEffect } from "react";
import * as THREE from "three";

export interface StarsBackgroundProps {
  className?: string;
  speedMultiplier?: number;
}

export const StarsBackground: React.FC<StarsBackgroundProps> = ({
  className = "",
  speedMultiplier = 1,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    let animId: number;
    let width = container.clientWidth || window.innerWidth;
    let height = container.clientHeight || window.innerHeight;

    // 1. Scene & Deep Space Fog
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x05070a, 0.006);

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 150);
    camera.position.set(0, 0, 5);

    // 3. WebGL Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    container.appendChild(renderer.domElement);

    // 4. Multi-Layered Starfield (matching Landing EarthGlobe exact spectral distribution)
    // A. Main Pinpoint Stars (3,200 stars)
    const starGeo = new THREE.BufferGeometry();
    const starCount = 3200;
    const starPositions = new Float32Array(starCount * 3);
    const starColors = new Float32Array(starCount * 3);

    const spectralColors = [
      new THREE.Color(0xffffff), // 50% Diamond White
      new THREE.Color(0xa2d9ff), // 25% Ice Blue
      new THREE.Color(0xffe6c2), // 15% Warm Amber
      new THREE.Color(0x00e5ff), // 10% Tactical Electric Cyan
    ];

    for (let i = 0; i < starCount; i++) {
      const idx = i * 3;
      const r = 20 + Math.random() * 65;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);

      starPositions[idx] = r * Math.sin(phi) * Math.cos(theta);
      starPositions[idx + 1] = r * Math.sin(phi) * Math.sin(theta);
      starPositions[idx + 2] = r * Math.cos(phi);

      const picked =
        i % 10 < 5
          ? spectralColors[0]
          : i % 10 < 8
          ? spectralColors[1]
          : i % 10 < 9
          ? spectralColors[2]
          : spectralColors[3];

      starColors[idx] = picked.r;
      starColors[idx + 1] = picked.g;
      starColors[idx + 2] = picked.b;
    }

    starGeo.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
    starGeo.setAttribute("color", new THREE.BufferAttribute(starColors, 3));

    const starMat = new THREE.PointsMaterial({
      size: 0.052,
      vertexColors: true,
      transparent: true,
      opacity: 0.88,
    });
    const starPoints = new THREE.Points(starGeo, starMat);
    scene.add(starPoints);

    // B. Prominent Bright Sparkling Stars (280 stars)
    const brightGeo = new THREE.BufferGeometry();
    const brightCount = 280;
    const brightPositions = new Float32Array(brightCount * 3);
    for (let i = 0; i < brightCount * 3; i += 3) {
      const r = 18 + Math.random() * 40;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);
      brightPositions[i] = r * Math.sin(phi) * Math.cos(theta);
      brightPositions[i + 1] = r * Math.sin(phi) * Math.sin(theta);
      brightPositions[i + 2] = r * Math.cos(phi);
    }
    brightGeo.setAttribute("position", new THREE.BufferAttribute(brightPositions, 3));
    const brightMat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.095,
      transparent: true,
      opacity: 0.95,
    });
    const brightPoints = new THREE.Points(brightGeo, brightMat);
    scene.add(brightPoints);

    // C. Deep Space Nebula Atmospheric Dust
    const nebulaGroup = new THREE.Group();
    scene.add(nebulaGroup);
    const nebulaColors = [0x041924, 0x08172c, 0x07221d];
    for (let k = 0; k < 4; k++) {
      const nebGeo = new THREE.BufferGeometry();
      const count = 120;
      const pos = new Float32Array(count * 3);
      for (let j = 0; j < count * 3; j += 3) {
        pos[j] = (Math.random() - 0.5) * 35;
        pos[j + 1] = (Math.random() - 0.5) * 25;
        pos[j + 2] = -15 - Math.random() * 25;
      }
      nebGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      const nebMat = new THREE.PointsMaterial({
        color: nebulaColors[k % nebulaColors.length],
        size: 0.6,
        transparent: true,
        opacity: 0.22,
        blending: THREE.AdditiveBlending,
      });
      nebulaGroup.add(new THREE.Points(nebGeo, nebMat));
    }

    // 5. Animation Loop
    const startTime = performance.now();
    const animate = () => {
      const elapsed = ((performance.now() - startTime) / 1000) * speedMultiplier;
      // Gentle spatial drift
      starPoints.rotation.y = elapsed * 0.015;
      starPoints.rotation.x = Math.sin(elapsed * 0.008) * 0.02;

      brightPoints.rotation.y = elapsed * 0.018;
      brightPoints.rotation.x = Math.cos(elapsed * 0.01) * 0.015;

      // Subtle twinkling on bright stars
      brightMat.opacity = 0.8 + Math.sin(elapsed * 3) * 0.2;

      nebulaGroup.rotation.y = elapsed * 0.006;

      renderer.render(scene, camera);
      animId = requestAnimationFrame(animate);
    };

    animate();

    // 6. Resize Handler
    const handleResize = () => {
      if (!container) return;
      const newW = container.clientWidth || window.innerWidth;
      const newH = container.clientHeight || window.innerHeight;
      camera.aspect = newW / newH;
      camera.updateProjectionMatrix();
      renderer.setSize(newW, newH);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animId);
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
      starGeo.dispose();
      starMat.dispose();
      brightGeo.dispose();
      brightMat.dispose();
      nebulaGroup.children.forEach((child) => {
        if (child instanceof THREE.Points) {
          child.geometry.dispose();
          if (Array.isArray(child.material)) {
            child.material.forEach((m) => m.dispose());
          } else {
            child.material.dispose();
          }
        }
      });
    };
  }, [speedMultiplier]);

  return <div ref={mountRef} className={className} />;
};
