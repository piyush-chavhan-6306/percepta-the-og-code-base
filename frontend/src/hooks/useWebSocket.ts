/**
 * Border Intelligence — Real-Time WebSocket Hook
 * Manages resilient auto-reconnecting WebSocket connection to /ws/events
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { WS_BASE_URL } from "../api/client";

export type WsConnectionStatus = "connected" | "connecting" | "disconnected" | "error";

export type BackendEventType =
  | "DETECTION"
  | "TRACKING"
  | "ZONE"
  | "RISK"
  | "EVIDENCE"
  | "ALERT"
  | "INCIDENT"
  | "HANDOFF"
  | "SYSTEM"
  | "alert"
  | "zone"
  | "tracking"
  | "detection"
  | "incident"
  | "system"
  | "pong";

export interface WsMessage {
  event_type: BackendEventType;
  event_id?: string;
  timestamp?: string;
  camera_id?: string;
  track_id?: string | null;
  incident_id?: string | null;
  severity?: string;
  message?: string;
  confidence?: number | null;
  payload?: any;
  [key: string]: any;
}

export function useWebSocket(onMessageReceived?: (msg: WsMessage) => void) {
  const [status, setStatus] = useState<WsConnectionStatus>("connecting");
  const [lastEvent, setLastEvent] = useState<WsMessage | null>(null);
  const [eventCount, setEventCount] = useState<number>(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef<number>(0);
  const pingIntervalRef = useRef<any>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const onMessageRef = useRef(onMessageReceived);

  onMessageRef.current = onMessageReceived;

  const connect = useCallback(() => {
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    setStatus("connecting");

    try {
      const ws = new WebSocket(WS_BASE_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        reconnectAttempts.current = 0;

        // Start ping keepalive every 25 seconds
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const data: WsMessage = JSON.parse(event.data);
          if (data.event_type === "pong" || data.type === "pong") {
            return;
          }
          setLastEvent(data);
          setEventCount((prev) => prev + 1);
          if (onMessageRef.current) {
            onMessageRef.current(data);
          }
        } catch (e) {
          console.warn("Failed to parse WebSocket message:", event.data);
        }
      };

      ws.onerror = (err) => {
        console.warn("WebSocket connection error:", err);
        setStatus("error");
      };

      ws.onclose = () => {
        setStatus("disconnected");
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);

        // Exponential backoff reconnect
        const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts.current), 10000);
        reconnectAttempts.current += 1;

        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      };
    } catch (err) {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    status,
    lastEvent,
    eventCount,
    reconnect: connect,
  };
}
