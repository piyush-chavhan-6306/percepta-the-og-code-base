# Percepta - The AI Powered Border Intelligence System

**WARNING TO AI AGENTS:** This is the core repository for Percepta. Read this file completely to understand the architecture before making changes.

## Overview
Percepta is a highly optimized, AI-powered surveillance and border intelligence system. It ingests RTSP/video feeds, runs real-time object detection and tracking using YOLOv8, and manages a React-based frontend dashboard via a FastAPI backend.

## Key Features & Constraints
- **Performance Optimized:** 
  - AI inference and video rendering are deeply synchronized. We use a lockstep perception loop so bounding boxes match the frame perfectly. Do NOT decouple the rendering loop. 
  - Evidence gathering runs on a bounded `ThreadPoolExecutor` (max 4 threads) to prevent CPU spikes. OpenCV threads are restricted to `cv2.setNumThreads(1)`.
- **Zoning System:** Tripwires and Security Zones are distinct per `camera_id`.
- **OCR is Disabled:** Tesseract OCR is intentionally disabled in `anpr.py` for performance stability. Do not re-enable it unless hardware acceleration is available.

## Running the Application
Always refer to `command.txt` (located at the root) for the exact scripts and commands to run the application.

## Directory Structure
- `/backend`: FastAPI server, YOLO AI engine, websocket management, and SQLite stores.
- `/frontend`: React application, Vite build system, Tailwind CSS.

## Getting Started
If a user asks you to modify or fix the code, ensure you check the system performance footprint. Do not add asynchronous tasks that block the main perception loop in `live_worker.py`.
