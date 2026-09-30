import React, { useRef, useEffect } from "react";
import * as THREE from "three";
import localEarthTexture from "@/assets/earth_atmos_2048.jpg";

export const earthChoreography = [
  // 00. Hero: Cinematic low horizon Earth, emerging from below viewport with atmospheric curve
  { at: 0, x: 0, y: -2.2, z: 0, scale: 1.35, rot: 3.25, tilt: 0.12, fov: 35, opacity: 1, light: 1.8 },
  // 01. Observe: Camera ascends above horizon, settles toward India border surveillance region
  { at: 0.1, x: 0.42, y: -0.05, z: 0.15, scale: 1.58, rot: 3.40, tilt: 0.14, fov: 34, opacity: 1, light: 2.1 },
  // 02. Detect: Smooth camera lock on India Border Sector-01 beacon on the left
  { at: 0.2, x: -0.40, y: 0.08, z: 0.20, scale: 1.68, rot: 3.52, tilt: 0.15, fov: 33, opacity: 1, light: 2.2 },
  // 03. Track: Camera dollies right and frames continuous entity route across border posts
  { at: 0.3, x: 0.40, y: 0.02, z: -0.15, scale: 1.52, rot: 3.65, tilt: 0.12, fov: 35, opacity: 1, light: 2.1 },
  // 04. Understand: Camera pivots as entity intersects restricted perimeter zone
  { at: 0.4, x: -0.38, y: 0.04, z: 0.05, scale: 1.60, rot: 3.78, tilt: 0.10, fov: 33, opacity: 1, light: 2.0 },
  // 05. Assess: Earth remains steady in background as focus shifts from WHERE to HOW RISKY
  { at: 0.5, x: 0.36, y: -0.04, z: -0.10, scale: 1.48, rot: 3.90, tilt: 0.08, fov: 36, opacity: 1, light: 1.9 },
  // 06. Evidence: Earth stays clear and steady
  { at: 0.6, x: -0.38, y: 0.02, z: -0.10, scale: 1.45, rot: 4.02, tilt: 0.08, fov: 36, opacity: 1, light: 1.9 },
  // 07. Incidents: Earth subtly re-centers as multiple signals consolidate into one incident
  { at: 0.7, x: 0.05, y: -0.02, z: -0.05, scale: 1.48, rot: 4.15, tilt: 0.08, fov: 35, opacity: 1, light: 1.9 },
  // 08. Command: Earth frames the right side with vivid atmospheric glow
  { at: 0.8, x: 0.38, y: 0.02, z: 0.00, scale: 1.50, rot: 4.28, tilt: 0.08, fov: 35, opacity: 1, light: 2.0 },
  // 09. Entrance to "Make sense of what matters": Earth is still fully visible and majestic
  { at: 0.89, x: 0.38, y: 0.02, z: 0.00, scale: 1.48, rot: 4.36, tilt: 0.08, fov: 35, opacity: 1, light: 2.0 },
  // 10. End of "Make sense of what matters": Earth zooms small into the distance until it vanishes into a tiny speck
  { at: 0.94, x: 0.38, y: 0.02, z: -1.00, scale: 0.70, rot: 4.44, tilt: 0.08, fov: 36, opacity: 0.75, light: 1.5 },
  { at: 0.98, x: 0.38, y: 0.02, z: -2.80, scale: 0.12, rot: 4.50, tilt: 0.08, fov: 38, opacity: 0.20, light: 0.6 },
  { at: 1.0, x: 0.38, y: 0.02, z: -4.50, scale: 0.001, rot: 4.54, tilt: 0.08, fov: 40, opacity: 0.0, light: 0.0 },
];

export function sampleEarth(progress: number) {
  const next = earthChoreography.findIndex((point) => point.at >= progress);
  const endIdx = next === -1 ? earthChoreography.length - 1 : Math.max(1, next);
  const startIdx = Math.max(0, endIdx - 1);
  const end = earthChoreography[endIdx];
  const start = earthChoreography[startIdx];
  const range = Math.max(0.001, end.at - start.at);
  const t = THREE.MathUtils.smoothstep(
    Math.min(1, Math.max(0, (progress - start.at) / range)),
    0,
    1
  );

  return {
    x: THREE.MathUtils.lerp(start.x, end.x, t),
    y: THREE.MathUtils.lerp(start.y, end.y, t),
    z: THREE.MathUtils.lerp(start.z, end.z, t),
    scale: THREE.MathUtils.lerp(start.scale, end.scale, t),
    rot: THREE.MathUtils.lerp(start.rot, end.rot, t),
    tilt: THREE.MathUtils.lerp(start.tilt, end.tilt, t),
    fov: THREE.MathUtils.lerp(start.fov, end.fov, t),
    opacity: THREE.MathUtils.lerp(start.opacity, end.opacity, t),
    light: THREE.MathUtils.lerp(start.light, end.light, t),
  };
}

export interface EarthGlobeProps {
  progress: number;
  className?: string;
}

/**
 * Procedural fallback canvas texture if satellite texture is unreachable.
 */
/**
 * Procedural fallback canvas texture if satellite texture is unreachable.
 */
function createFallbackCanvasTexture(): THREE.CanvasTexture {
  const width = 2048;
  const height = 1024;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;

  const oceanGrad = ctx.createLinearGradient(0, 0, 0, height);
  oceanGrad.addColorStop(0, "#08131e");
  oceanGrad.addColorStop(0.5, "#0b1c2e");
  oceanGrad.addColorStop(1, "#050d15");
  ctx.fillStyle = oceanGrad;
  ctx.fillRect(0, 0, width, height);

  ctx.fillStyle = "#2d3a2e";
  ctx.fillRect(200, 150, 450, 300); // Americas rough
  ctx.fillRect(450, 480, 300, 400);
  ctx.fillRect(950, 180, 600, 300); // Eurasia
  ctx.fillRect(1050, 420, 400, 380); // Africa
  ctx.fillRect(1500, 560, 320, 260); // Australia

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  return texture;
}

/**
 * Creates 3D Tactical India Border Defense Beacon on the Globe
 */
function createIndiaMarkerGroup(): { group: THREE.Group; pulseRing: THREE.Mesh; pulseDot: THREE.Mesh } {
  const indiaGroup = new THREE.Group();

  // Geographic anchor: Northern India / Border Sector ~ 28.6° N, 77.2° E
  const lat = 28.6;
  const lon = 77.2;
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  const radius = 1.004;

  const pos = new THREE.Vector3(
    -(radius * Math.cos(theta) * Math.sin(phi)),
    radius * Math.cos(phi),
    radius * Math.sin(theta) * Math.sin(phi)
  );

  indiaGroup.position.copy(pos);
  const normal = pos.clone().normalize();
  indiaGroup.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);

  // 1. Central Core Marker Dot (Glowing Cyan)
  const dotGeo = new THREE.SphereGeometry(0.016, 16, 16);
  const dotMat = new THREE.MeshBasicMaterial({ color: 0x00e5ff });
  const pulseDot = new THREE.Mesh(dotGeo, dotMat);
  pulseDot.position.set(0, 0, 0.005);
  indiaGroup.add(pulseDot);

  // 2. Tactical Radar Concentric Pulse Ring
  const ringGeo = new THREE.RingGeometry(0.024, 0.044, 32);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x00e5ff,
    transparent: true,
    opacity: 0.85,
    side: THREE.DoubleSide,
  });
  const pulseRing = new THREE.Mesh(ringGeo, ringMat);
  pulseRing.position.set(0, 0, 0.003);
  indiaGroup.add(pulseRing);

  // 3. Outer Emerald DEFCON Ring
  const outerRingGeo = new THREE.RingGeometry(0.062, 0.072, 32);
  const outerRingMat = new THREE.MeshBasicMaterial({
    color: 0x00e676,
    transparent: true,
    opacity: 0.65,
    side: THREE.DoubleSide,
  });
  const outerRing = new THREE.Mesh(outerRingGeo, outerRingMat);
  outerRing.position.set(0, 0, 0.002);
  indiaGroup.add(outerRing);

  // 4. Tactical Radar Crosshairs
  const crossMat = new THREE.LineBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.6 });
  const lineHGeo = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-0.085, 0, 0.004),
    new THREE.Vector3(0.085, 0, 0.004),
  ]);
  const lineVGeo = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, -0.085, 0.004),
    new THREE.Vector3(0, 0.085, 0.004),
  ]);
  indiaGroup.add(new THREE.Line(lineHGeo, crossMat));
  indiaGroup.add(new THREE.Line(lineVGeo, crossMat));

  // 5. Tactical Canvas Badge Sprite: "INDIA // BORDER C2"
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 140;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = "rgba(5, 7, 10, 0.88)";
    ctx.strokeStyle = "#00e5ff";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.roundRect(8, 8, 496, 124, 12);
    ctx.fill();
    ctx.stroke();

    // Corner accents
    ctx.fillStyle = "#00e676";
    ctx.fillRect(8, 8, 18, 4);
    ctx.fillRect(8, 8, 4, 18);
    ctx.fillRect(486, 8, 18, 4);
    ctx.fillRect(500, 8, 4, 18);

    // Text
    ctx.font = "bold 38px 'Orbitron', 'Barlow Condensed', sans-serif";
    ctx.fillStyle = "#ffffff";
    ctx.fillText("INDIA // BORDER C2", 28, 56);

    ctx.font = "26px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#00e5ff";
    ctx.fillText("SECTOR-01 · 28.6°N 77.2°E", 28, 102);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const spriteMat = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthTest: false,
    });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.position.set(0, 0.12, 0.06);
    sprite.scale.set(0.38, 0.11, 1);
    indiaGroup.add(sprite);
  }

  return { group: indiaGroup, pulseRing, pulseDot };
}

export const EarthGlobe: React.FC<EarthGlobeProps> = ({ progress, className = "" }) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef(progress);
  progressRef.current = progress;

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    let animId: number;
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || window.innerHeight;

    // 1. Scene & Deep Space Fog
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x05070a, 0.007);

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(35, width / height, 0.1, 120);
    camera.position.set(0, 0, 4.8);

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    container.appendChild(renderer.domElement);

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0xd7f0e7, 0.5);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xf6e9cd, 2.3);
    dirLight.position.set(-3.5, 2.2, 4.2);
    scene.add(dirLight);

    const pointLight = new THREE.PointLight(0x00e5ff, 1.4);
    pointLight.position.set(3, -2, 2);
    scene.add(pointLight);

    const choreoLight = new THREE.PointLight(0xd7f0e7, 1.8, 12);
    choreoLight.position.set(-2, 1, 3);
    scene.add(choreoLight);

    // 5. Rich Multi-Layered Starfield
    // A. Main Pinpoint Stars (2,800 stars with realistic spectral color distribution)
    const starGeo = new THREE.BufferGeometry();
    const starCount = 2800;
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
      const r = 24 + Math.random() * 55;
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
      size: 0.048,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
    });
    const starPoints = new THREE.Points(starGeo, starMat);
    scene.add(starPoints);

    // B. Prominent Bright Sparkling Stars (240 stars)
    const brightGeo = new THREE.BufferGeometry();
    const brightCount = 240;
    const brightPositions = new Float32Array(brightCount * 3);
    for (let i = 0; i < brightCount * 3; i += 3) {
      const r = 20 + Math.random() * 32;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);
      brightPositions[i] = r * Math.sin(phi) * Math.cos(theta);
      brightPositions[i + 1] = r * Math.sin(phi) * Math.sin(theta);
      brightPositions[i + 2] = r * Math.cos(phi);
    }
    brightGeo.setAttribute("position", new THREE.BufferAttribute(brightPositions, 3));
    const brightMat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.085,
      transparent: true,
      opacity: 0.95,
    });
    const brightPoints = new THREE.Points(brightGeo, brightMat);
    scene.add(brightPoints);

    // C. Deep Space Nebula Clusters (Atmospheric Cosmic Dust)
    const nebulaGroup = new THREE.Group();
    scene.add(nebulaGroup);
    const nebulaColors = [0x08262a, 0x0a1626, 0x140e22];
    for (let i = 0; i < 4; i++) {
      const nGeo = new THREE.BufferGeometry();
      const nParticles = 140;
      const nPos = new Float32Array(nParticles * 3);
      const center = new THREE.Vector3(
        (Math.random() - 0.5) * 30,
        (Math.random() - 0.5) * 20,
        -25 - Math.random() * 15
      );
      for (let j = 0; j < nParticles * 3; j += 3) {
        nPos[j] = center.x + (Math.random() - 0.5) * 12;
        nPos[j + 1] = center.y + (Math.random() - 0.5) * 10;
        nPos[j + 2] = center.z + (Math.random() - 0.5) * 8;
      }
      nGeo.setAttribute("position", new THREE.BufferAttribute(nPos, 3));
      const nMat = new THREE.PointsMaterial({
        color: nebulaColors[i % nebulaColors.length],
        size: 0.5,
        transparent: true,
        opacity: 0.06,
        blending: THREE.AdditiveBlending,
      });
      nebulaGroup.add(new THREE.Points(nGeo, nMat));
    }

    // 6. Earth Group & Meshes
    const earthGroup = new THREE.Group();
    scene.add(earthGroup);

    // Earth Texture loading (Local asset prioritized, fallback to CDN, fallback to canvas)
    const textureLoader = new THREE.TextureLoader();
    let earthTexture: THREE.Texture;
    try {
      earthTexture = textureLoader.load(
        localEarthTexture || "https://threejs.org/examples/textures/planets/earth_atmos_2048.jpg",
        () => {
          if (earthMat) earthMat.needsUpdate = true;
        },
        undefined,
        () => {
          if (earthMat) {
            earthMat.map = createFallbackCanvasTexture();
            earthMat.needsUpdate = true;
          }
        }
      );
    } catch {
      earthTexture = createFallbackCanvasTexture();
    }

    const sphereGeo = new THREE.SphereGeometry(1, 64, 64);
    const earthMat = new THREE.MeshStandardMaterial({
      map: earthTexture,
      transparent: true,
      opacity: 1,
      roughness: 0.88,
      metalness: 0.05,
    });
    const earthMesh = new THREE.Mesh(sphereGeo, earthMat);
    earthGroup.add(earthMesh);

    // 7. Tactical India Border Defense Beacon & C2 Reticle
    const { group: indiaMarker, pulseRing: indiaPulseRing, pulseDot: indiaPulseDot } = createIndiaMarkerGroup();
    earthMesh.add(indiaMarker);

    // Atmospheric outer glow shell
    const atmosGeo = new THREE.SphereGeometry(1.035, 48, 48);
    const atmosMat = new THREE.MeshBasicMaterial({
      color: 0x00e5ff,
      transparent: true,
      opacity: 0.14,
      side: THREE.BackSide,
    });
    const atmosMesh = new THREE.Mesh(atmosGeo, atmosMat);
    earthGroup.add(atmosMesh);

    // Initial positioning
    const initialTarget = sampleEarth(progressRef.current);
    earthGroup.position.set(initialTarget.x, initialTarget.y, initialTarget.z);
    earthGroup.scale.setScalar(initialTarget.scale);
    earthGroup.rotation.set(initialTarget.tilt, initialTarget.rot, 0);

    // 8. Cursor Responsive State & Listeners
    const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };

    const handleMouseMove = (e: MouseEvent) => {
      // Normalized coordinates (-1 to 1)
      mouse.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });

    // 9. Animation Loop with smooth dampening & Cursor Parallax
    let clock = new THREE.Clock();

    const animate = () => {
      animId = requestAnimationFrame(animate);
      const delta = Math.min(clock.getDelta(), 0.1);
      const elapsedTime = clock.getElapsedTime();
      const target = sampleEarth(progressRef.current);

      // Smooth cursor lerp / damp
      mouse.x = THREE.MathUtils.damp(mouse.x, mouse.targetX, 3.5, delta);
      mouse.y = THREE.MathUtils.damp(mouse.y, mouse.targetY, 3.5, delta);

      // Camera cursor responsiveness
      camera.position.x = mouse.x * 0.35;
      camera.position.y = mouse.y * 0.25;
      camera.lookAt(0, 0, 0);

      // Earth position & scale damp
      earthGroup.position.x = THREE.MathUtils.damp(earthGroup.position.x, target.x, 4, delta);
      earthGroup.position.y = THREE.MathUtils.damp(earthGroup.position.y, target.y, 4, delta);
      earthGroup.position.z = THREE.MathUtils.damp(earthGroup.position.z, target.z, 4, delta);
      earthGroup.scale.setScalar(
        THREE.MathUtils.damp(earthGroup.scale.x, target.scale, 4, delta)
      );

      // Earth rotation + cursor reaction tilt
      earthGroup.rotation.x = THREE.MathUtils.damp(
        earthGroup.rotation.x,
        target.tilt + mouse.y * 0.08,
        4,
        delta
      );
      earthGroup.rotation.y =
        THREE.MathUtils.damp(earthGroup.rotation.y, target.rot, 3.2, delta) +
        Math.sin(elapsedTime * 0.22) * 0.002;
      earthGroup.rotation.z = THREE.MathUtils.damp(
        earthGroup.rotation.z,
        -mouse.x * 0.08,
        4,
        delta
      );

      // Tactical Radar Pulse Animation over India
      const pulseCycle = (elapsedTime * 1.8) % 1;
      indiaPulseRing.scale.setScalar(1 + pulseCycle * 1.6);
      (indiaPulseRing.material as THREE.MeshBasicMaterial).opacity = Math.max(0, 0.85 * (1 - pulseCycle));
      indiaPulseDot.scale.setScalar(1 + Math.sin(elapsedTime * 5) * 0.25);

      // Camera FOV damp
      camera.fov = THREE.MathUtils.damp(camera.fov, target.fov, 3.5, delta);
      camera.updateProjectionMatrix();

      // Opacity and lighting
      earthMat.opacity = THREE.MathUtils.damp(earthMat.opacity, target.opacity, 5, delta);
      atmosMat.opacity = THREE.MathUtils.damp(atmosMat.opacity, target.opacity * 0.12, 5, delta);
      choreoLight.intensity = target.light;
      earthGroup.visible = earthMat.opacity > 0.005 && earthGroup.scale.x > 0.005;

      // Stars parallax & gentle shimmer
      starPoints.rotation.y = mouse.x * 0.03 + elapsedTime * 0.003;
      starPoints.rotation.x = -mouse.y * 0.02;

      brightPoints.rotation.y = mouse.x * 0.04 + elapsedTime * 0.005;
      brightPoints.rotation.x = -mouse.y * 0.025;
      brightMat.opacity = 0.85 + Math.sin(elapsedTime * 2.5) * 0.15; // Shimmer

      renderer.render(scene, camera);
    };

    animate();

    // 10. Responsive Resize
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
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(animId);
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
      sphereGeo.dispose();
      earthMat.dispose();
      atmosGeo.dispose();
      atmosMat.dispose();

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
  }, []);

  return <div ref={mountRef} className={`w-full h-full ${className}`} />;
};
