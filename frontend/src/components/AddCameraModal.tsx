import { useState, useRef, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import {
  Upload,
  Camera,
  Wifi,
  FileVideo,
  Check,
  X,
  Moon,
  Flame,
  Video,
  AlertCircle,
} from "lucide-react";
import { API_BASE_URL } from "@/api/client";

interface AddCameraModalProps {
  open?: boolean;
  onClose: () => void;
  onCameraAdded?: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function AddCameraModal({ open = true, onClose, onCameraAdded }: AddCameraModalProps) {
  const [tab, setTab] = useState("upload");
  const [cameraName, setCameraName] = useState("");
  const [modality, setModality] = useState<string>("STANDARD");
  const [rtspUrl, setRtspUrl] = useState("");
  const [webcamIndex, setWebcamIndex] = useState("0");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setCameraName("");
    setRtspUrl("");
    setWebcamIndex("0");
    setSelectedFile(null);
    setIsDragging(false);
    setIsUploading(false);
    setUploadProgress(0);
    setUploadError(null);
    setModality("STANDARD");
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleFileSelect = useCallback((file: File) => {
    setSelectedFile(file);
    setUploadError(null);
    if (!cameraName.trim()) {
      const baseName = file.name.replace(/\.[^.]+$/, "").replace(/[_-]/g, " ");
      setCameraName(baseName);
    }
  }, [cameraName]);

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  };

  const removeFile = () => {
    setSelectedFile(null);
    setUploadProgress(0);
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const uploadWithProgress = async (file: File, name: string): Promise<any> => {
    return new Promise((resolve, reject) => {
      const derivedCameraType = modality === "IR_NIGHT" ? "IR" : modality === "THERMAL" ? "THERMAL" : "RGB";
      const formData = new FormData();
      formData.append("file", file);
      formData.append("name", name);
      formData.append("location_label", "Sector Surveillance");
      formData.append("modality", modality);
      formData.append("camera_type", derivedCameraType);

      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          setUploadProgress(percent);
        }
      });

      xhr.addEventListener("load", async () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText);
            resolve(data);
          } catch {
            resolve({ camera_id: `CAM-${Date.now().toString().slice(-4)}` });
          }
        } else {
          let errMsg = `Upload failed (HTTP ${xhr.status})`;
          try {
            const body = JSON.parse(xhr.responseText);
            if (body.detail) errMsg = body.detail;
          } catch {}
          reject(new Error(errMsg));
        }
      });

      xhr.addEventListener("error", () => reject(new Error("Network error during upload. Please check backend connection.")));
      xhr.addEventListener("abort", () => reject(new Error("Upload cancelled")));

      const uploadUrl = API_BASE_URL ? `${API_BASE_URL}/api/cameras/upload` : "/api/cameras/upload";
      xhr.open("POST", uploadUrl);
      xhr.send(formData);
    });
  };

  const handleSubmit = async () => {
    if (!cameraName.trim()) return;

    setIsUploading(true);
    setUploadError(null);
    setUploadProgress(0);

    try {
      if (tab === "upload" && selectedFile) {
        // Direct stream upload of ANY file
        const record = await uploadWithProgress(selectedFile, cameraName.trim());
        if (record) {
          onCameraAdded?.();
          handleClose();
        }
      } else {
        // RTSP or Webcam
        const cleanId = `CAM-${Date.now().toString().slice(-4)}`;
        let sourceType = "rtsp";
        let url: string | undefined = rtspUrl;
        let devIdx: number | undefined = undefined;

        if (tab === "webcam") {
          sourceType = "webcam";
          devIdx = parseInt(webcamIndex, 10) || 0;
          url = undefined;
        }

        const derivedCameraType = modality === "IR_NIGHT" ? "IR" : modality === "THERMAL" ? "THERMAL" : "RGB";
        const registerUrl = API_BASE_URL ? `${API_BASE_URL}/api/cameras/register` : "/api/cameras/register";
        const res = await fetch(registerUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            camera_id: cleanId,
            name: cameraName.trim(),
            source_type: sourceType,
            source_url: url,
            device_index: devIdx,
            location_label: "Active Sector",
            modality: modality,
            camera_type: derivedCameraType,
          }),
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `Registration failed (HTTP ${res.status})`);
        }

        onCameraAdded?.();
        handleClose();
      }
    } catch (err: any) {
      console.error("Failed to add camera:", err);
      setUploadError(err.message || "Failed to register camera feed");
    } finally {
      setIsUploading(false);
    }
  };

  const canSubmit =
    cameraName.trim() &&
    ((tab === "upload" && selectedFile) ||
      tab === "webcam" ||
      (tab === "rtsp" && rtspUrl.trim()));

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="sm:max-w-[520px] border-white/10 bg-[#0d1322] shadow-2xl text-foreground font-mono">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base font-bold">
            <div className="w-8 h-8 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center text-primary">
              <Camera className="w-4 h-4" />
            </div>
            REGISTER SURVEILLANCE FEED
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground font-mono">
            Connect an IP/RTSP camera, optical webcam, or upload any video file for AI perception.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {/* Camera Name */}
          <div className="space-y-1.5">
            <Label htmlFor="camera-name" className="text-xs font-semibold text-foreground">
              Camera / Post Name
            </Label>
            <Input
              id="camera-name"
              placeholder="e.g. Sector 9 North Fence, Checkpoint Alpha"
              value={cameraName}
              onChange={(e) => setCameraName(e.target.value)}
              className="bg-black/50 border-white/10 text-xs font-mono"
            />
          </div>

          {/* Sensor Modality */}
          <div className="space-y-1.5">
            <Label className="text-xs font-semibold text-foreground">Sensor Modality</Label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setModality("STANDARD")}
                className={`p-2.5 rounded-xl border text-left text-xs font-mono transition-all flex flex-col gap-1 ${
                  modality === "STANDARD"
                    ? "bg-cyan-500/20 border-cyan-500 text-cyan-300 shadow-md shadow-cyan-500/10"
                    : "bg-black/40 border-white/10 text-muted-foreground hover:text-foreground"
                }`}
              >
                <Video className="w-4 h-4 text-cyan-400" />
                <span className="font-bold">STANDARD RGB</span>
                <span className="text-[9px] opacity-70">Optical CCTV</span>
              </button>

              <button
                type="button"
                onClick={() => setModality("IR_NIGHT")}
                className={`p-2.5 rounded-xl border text-left text-xs font-mono transition-all flex flex-col gap-1 ${
                  modality === "IR_NIGHT"
                    ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 shadow-md shadow-emerald-500/10"
                    : "bg-black/40 border-white/10 text-muted-foreground hover:text-foreground"
                }`}
              >
                <Moon className="w-4 h-4 text-emerald-400" />
                <span className="font-bold">IR NIGHT</span>
                <span className="text-[9px] opacity-70">Night Vision</span>
              </button>

              <button
                type="button"
                onClick={() => setModality("THERMAL")}
                className={`p-2.5 rounded-xl border text-left text-xs font-mono transition-all flex flex-col gap-1 ${
                  modality === "THERMAL"
                    ? "bg-orange-500/20 border-orange-500 text-orange-300 shadow-md shadow-orange-500/10"
                    : "bg-black/40 border-white/10 text-muted-foreground hover:text-foreground"
                }`}
              >
                <Flame className="w-4 h-4 text-orange-400" />
                <span className="font-bold">THERMAL IR</span>
                <span className="text-[9px] opacity-70">Heat Radiometry</span>
              </button>
            </div>
          </div>

          {/* Source Tabs */}
          <Tabs value={tab} onValueChange={setTab} className="w-full">
            <TabsList className="grid grid-cols-3 bg-black/60 border border-white/10">
              <TabsTrigger value="upload" className="text-xs font-mono data-[state=active]:bg-primary">
                <FileVideo className="w-3.5 h-3.5 mr-1" /> Video File
              </TabsTrigger>
              <TabsTrigger value="rtsp" className="text-xs font-mono data-[state=active]:bg-primary">
                <Wifi className="w-3.5 h-3.5 mr-1" /> RTSP IP
              </TabsTrigger>
              <TabsTrigger value="webcam" className="text-xs font-mono data-[state=active]:bg-primary">
                <Camera className="w-3.5 h-3.5 mr-1" /> Webcam
              </TabsTrigger>
            </TabsList>

            {/* Video File Tab */}
            <TabsContent value="upload" className="space-y-3 mt-3">
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*,*"
                onChange={handleFileInputChange}
                className="hidden"
              />

              {!selectedFile ? (
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                    isDragging
                      ? "border-primary bg-primary/10"
                      : "border-white/10 hover:border-primary/50 bg-black/30 hover:bg-black/50"
                  }`}
                >
                  <Upload className="w-10 h-10 text-primary/70 mx-auto mb-2" />
                  <p className="text-xs font-semibold text-foreground">
                    Drop any video file here or click to browse
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Accepts any video format (MP4, AVI, MOV, MKV, WebM, TS, etc.)
                  </p>
                </div>
              ) : (
                <div className="p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-950/20 flex items-center justify-between">
                  <div className="flex items-center gap-3 overflow-hidden">
                    <div className="w-10 h-10 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center shrink-0">
                      <FileVideo className="w-5 h-5 text-emerald-400" />
                    </div>
                    <div className="overflow-hidden">
                      <p className="text-xs font-bold text-foreground truncate">{selectedFile.name}</p>
                      <p className="text-[10px] text-muted-foreground">{formatFileSize(selectedFile.size)}</p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={removeFile}
                    className="h-8 w-8 text-muted-foreground hover:text-foreground shrink-0"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              )}

              {/* Upload Progress Bar */}
              {isUploading && (
                <div className="space-y-1.5 p-3 rounded-xl bg-black/40 border border-white/10">
                  <div className="flex justify-between text-[10px] font-mono text-muted-foreground">
                    <span>Streaming to Perception Pipeline...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <Progress value={uploadProgress} className="h-1.5" />
                </div>
              )}
            </TabsContent>

            {/* RTSP IP Tab */}
            <TabsContent value="rtsp" className="space-y-3 mt-3">
              <div className="space-y-1.5">
                <Label htmlFor="rtsp-url" className="text-xs text-muted-foreground">
                  RTSP Stream URL
                </Label>
                <Input
                  id="rtsp-url"
                  placeholder="rtsp://admin:pass@192.168.1.100:554/stream1"
                  value={rtspUrl}
                  onChange={(e) => setRtspUrl(e.target.value)}
                  className="bg-black/50 border-white/10 text-xs font-mono"
                />
              </div>
            </TabsContent>

            {/* Webcam Tab */}
            <TabsContent value="webcam" className="space-y-3 mt-3">
              <div className="space-y-1.5">
                <Label htmlFor="webcam-index" className="text-xs text-muted-foreground">
                  USB Camera Index
                </Label>
                <Input
                  id="webcam-index"
                  type="number"
                  min="0"
                  max="8"
                  value={webcamIndex}
                  onChange={(e) => setWebcamIndex(e.target.value)}
                  className="bg-black/50 border-white/10 text-xs font-mono"
                />
              </div>
            </TabsContent>
          </Tabs>

          {/* Upload Error Banner */}
          {uploadError && (
            <div className="p-3 rounded-xl bg-red-950/40 border border-red-800/40 text-red-300 font-mono text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{uploadError}</span>
            </div>
          )}
        </div>

        {/* Modal Actions */}
        <div className="flex items-center justify-end gap-2 mt-4 pt-3 border-t border-white/10">
          <Button variant="ghost" size="sm" onClick={handleClose} className="font-mono text-xs">
            CANCEL
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={!canSubmit || isUploading}
            className="bg-primary hover:bg-primary/90 text-primary-foreground font-mono text-xs font-bold flex items-center gap-1.5"
          >
            {isUploading ? (
              <div className="w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <Check className="w-3.5 h-3.5" />
                <span>START INGESTION</span>
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
