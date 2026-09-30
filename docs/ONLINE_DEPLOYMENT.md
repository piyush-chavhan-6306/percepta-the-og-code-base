# PERCEPTA ONLINE DEPLOYMENT GUIDE
**Zero-Cost, No-Credit-Card-Required Cloud-Hybrid Deployment**

This guide provides complete, production-ready instructions for deploying PERCEPTA Online using 100% free-tier infrastructure (Render, Vercel, Neon PostgreSQL, Supabase Auth). None of these platforms require a credit card for setup or normal usage.

---

## 1. Cloud-Hybrid Architecture Overview

```
                                PERCEPTA ONLINE
                                       │
                  ┌────────────────────┴────────────────────┐
                  │                                         │
             EDGE (Local)                              CLOUD (Free Tiers)
                  │                                         │
            Camera Ingest                              Supabase Auth
                  │                                         │
            YOLOv8 & ONNX                             Neon PostgreSQL
                  │                                         │
              ByteTrack                                FastAPI Backend (Render)
                  │                                         │
         Zones & Tripwires                            React Frontend (Vercel)
                  │                                         │
        Incident & Threat Engine                       Grounded Copilot
                  │                                         │
            Evidence Hash                               Chunked Upload
                  │                                         │
                  └──────────── Sync & Metadata ────────────┘
```

The system operates on an **Edge-First, Cloud-Hybrid** model:
- **Edge Node:** Heavy vision inference (YOLOv8, ByteTrack, zone evaluation, optical diagnostics) executes locally or on dedicated edge hardware.
- **Cloud Layer:** Multi-tenant metadata, tenant isolation, incidents, alerts, forensic evidence records, grounded Copilot intelligence, and global C2 command and control.

---

## 2. Free-Tier Technology Stack Summary

| Component | Provider | Tier | Credit Card Required? |
| :--- | :--- | :--- | :--- |
| **Relational Database** | [Neon](https://neon.tech) | Free Tier (0.5 GiB, serverless compute) | **NO** |
| **Authentication** | [Supabase](https://supabase.com) | Free Tier (50,000 monthly active users) | **NO** |
| **Backend API & WebSockets** | [Render](https://render.com) | Free Web Service (512 MB RAM) | **NO** |
| **Frontend Web C2** | [Vercel](https://vercel.com) | Hobby Free Plan (Unlimited previews) | **NO** |
| **Inference & Vision** | Local Edge Hardware | Runs on local camera ingest node | **N/A** |

---

## 3. GitHub Setup

1. Initialize or connect your Git repository:
   ```bash
   git init
   git add .
   git commit -m "feat(percepta): production cloud-hybrid c2"
   ```
2. Create a repository on GitHub (e.g., `percepta-defence-c2`).
3. Push your repository:
   ```bash
   git remote add origin https://github.com/your-username/percepta-defence-c2.git
   git branch -M main
   git push -u origin main
   ```
4. Ensure `.env` is listed in `.gitignore`. **NEVER commit production database credentials or service-role keys.**

---

## 4. Neon PostgreSQL Setup (Database)

1. Sign up at [https://neon.tech](https://neon.tech) using your GitHub account.
2. Click **Create Project**:
   - **Project Name:** `percepta-defence-cloud`
   - **Region:** Choose the region closest to your operations.
   - **PostgreSQL Version:** 16 (default).
3. Copy the pooled connection string:
   ```
   postgresql://percepta_user:secret_password@ep-sample-12345.us-east-2.aws.neon.tech/percepta_cloud?sslmode=require
   ```
4. PERCEPTA's `online/database/neon_adapter.py` automatically converts `postgresql://` to async `postgresql+asyncpg://` at runtime.
5. **Schema Initialization:** Tables are auto-generated on startup via SQLAlchemy declarative models (`online.database.models`). To run schema initialization explicitly:
   ```bash
   python -c "import asyncio; from online.database.neon_adapter import init_cloud_db; asyncio.run(init_cloud_db())"
   ```

---

## 5. Supabase Auth Setup (Authentication)

1. Sign up at [https://supabase.com](https://supabase.com) with GitHub.
2. Click **New Project**:
   - **Name:** `percepta-auth`
   - **Database Password:** Enter a secure password.
   - **Pricing Plan:** Free ($0/month).
3. Under **Project Settings** $\to$ **API**:
   - Copy **Project URL** (`https://your-ref.supabase.co`).
   - Copy **anon public key** (`eyJhbGciOi...`).
   - Copy **service_role secret key** (Backend-only; never share in frontend).
4. Under **Authentication** $\to$ **URL Configuration**:
   - Set **Site URL** to your frontend domain (`https://percepta-c2.vercel.app` or `http://localhost:5173`).
   - Add Redirect URLs: `https://percepta-c2.vercel.app/**`, `http://localhost:5173/**`.

---

## 6. Render Backend Deployment

1. Sign in to [https://render.com](https://render.com) using GitHub.
2. Click **New +** $\to$ **Web Service**:
   - **Repository:** Select `percepta-defence-c2`.
   - **Root Directory:** Leave blank.
   - **Environment:** `Python 3`.
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     uvicorn online.backend.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type:** Free (512 MB).
3. Configure **Environment Variables** in Render Dashboard:
   ```env
   APP_ENV=production
   DEMO_MODE=false
   PORT=10000
   DATABASE_URL=postgresql+asyncpg://percepta_user:secret_password@ep-sample-12345.us-east-2.aws.neon.tech/percepta_cloud?ssl=require
   SUPABASE_URL=https://your-ref.supabase.co
   SUPABASE_ANON_KEY=your-supabase-anon-key
   SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
   CORS_ORIGINS=https://percepta-c2.vercel.app,http://localhost:5173
   RETENTION_HOURS=24
   STORAGE_BACKEND=local
   STORAGE_DIR=./storage
   ```
4. Click **Deploy Web Service**. Render provisions your backend URL: `https://percepta-backend.onrender.com`.

---

## 7. Vercel Frontend Deployment

1. Sign in to [https://vercel.com](https://vercel.com) using GitHub.
2. Click **Add New...** $\to$ **Project**:
   - **Root Directory:** `online/frontend`
   - **Framework Preset:** `Vite`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
3. Configure **Environment Variables** in Vercel:
   ```env
   VITE_API_URL=https://percepta-backend.onrender.com
   VITE_WS_URL=wss://percepta-backend.onrender.com/ws/events
   VITE_SUPABASE_URL=https://your-ref.supabase.co
   VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
   ```
4. Click **Deploy**. Vercel will build and assign your production URL: `https://percepta-c2.vercel.app`.

---

## 8. CORS & WebSockets Configuration

- **CORS:** The backend dynamically allows origins configured in `CORS_ORIGINS`. In production, this includes your Vercel domain (`https://percepta-c2.vercel.app`).
- **WebSockets:** WebSockets operate under `/ws/events` with automatic reconnection, heartbeat ping/pong, and token validation via query param `?token=<jwt>`.

---

## 9. Storage, Chunked Upload & Evidence Retention

- **Chunked Video Upload:** Large surveillance video files (1 GB, 2 GB+) are uploaded via streaming chunks through `/api/upload/init`, `/api/upload/chunk`, and `/api/upload/complete` without blowing up browser or backend memory.
- **Evidence Persistence:** Incident evidence captures compute SHA-256 hashes and store files through `EvidenceStorage`.
- **Retention Purge:** Raw footage auto-purges after `RETENTION_HOURS` (e.g. 24h). Forensic evidence attached to incidents is permanently flagged (`is_permanent=True`) and preserved.

---

## 10. Asynchronous Queue System

Background tasks are managed by `OnlineQueueManager` (`online/services/queue_manager.py`):
- Supported States: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `RETRYING`.
- Handlers manage:
  - Video chunk assembly and SHA-256 integrity verification.
  - Snapshot thumbnail generation and JPEG compression.
  - Raw storage retention pruning.
  - Edge-to-cloud synchronization reconciliation.

---

## 11. Production Verification Checklist

1. [ ] **Health Endpoint:** Visit `https://percepta-backend.onrender.com/api/health` $\to$ Returns `{"status": "healthy"}`.
2. [ ] **Landing Page:** Visit `https://percepta-c2.vercel.app/` $\to$ Verify cinematic landing page and "ENTER C2" CTA.
3. [ ] **Authentication Flow:** Click "ENTER C2" $\to$ Redirects to `/auth` $\to$ Log in with Supabase credentials.
4. [ ] **User Isolation:** Log in as User A and User B $\to$ Verify User A cannot view User B's cameras or incidents.
5. [ ] **Demo Camera:** Confirm CAM-01 displays `virat_cctv.mp4` as explicit `[DEMO SOURCE]`.
6. [ ] **Analysis Controls:** Test Start Analysis $\to$ Stop Analysis $\to$ Start Analysis again.
7. [ ] **Acknowledgement:** Click "Acknowledge" from Alert Table and Incident Inspector $\to$ Verify single unified operation updates DB and broadcast event.
8. [ ] **Grounded Copilot:** Ask questions about CAM-01, active alerts, trust score, and blind spots $\to$ Copilot calls structured tools and returns real telemetry.
9. [ ] **Multi-Camera Grid:** Switch between 1×1, 2×2, 3×3 layouts $\to$ Empty slots render standby states without fabricating cameras.

---

## 12. Troubleshooting & FAQ

### Issue: Render Free-Tier Cold Starts
- **Symptom:** First request to backend takes 30-50 seconds.
- **Cause:** Render free tier spins down after 15 minutes of inactivity.
- **Solution:** Standard behavior on free plans. Once awake, performance is instant. Keep-alive ping crons can optionally maintain readiness.

### Issue: Neon Connection Errors
- **Symptom:** `asyncpg.exceptions.InvalidPasswordError` or SSL errors.
- **Fix:** Ensure `?ssl=require` is present in the `DATABASE_URL` query string and that the driver is `postgresql+asyncpg://`.

### Issue: WebSocket Fails to Connect
- **Symptom:** Frontend status displays `WEBSOCKET DISCONNECTED`.
- **Fix:** Verify `VITE_WS_URL` uses the `wss://` protocol instead of `ws://` in production, matching the HTTPS backend hostname.
