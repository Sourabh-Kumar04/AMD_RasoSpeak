"use client";

import { useState, useCallback, useEffect, useRef } from "react";

interface AgentEvent {
  type: string;
  agentId?: string;
  agentType?: string;
  confidence?: number;
  token?: string;
  tool?: string;
  reasoning?: string;
  timestamp: number;
}

interface AgentStreamState {
  events: AgentEvent[];
  status: "idle" | "connecting" | "connected" | "thinking" | "error";
  activeAgents: number;
  workflowsRunning: number;
}

interface UseAgentStreamReturn {
  events: AgentEvent[];
  status: AgentStreamState["status"];
  activeAgents: number;
  workflowsRunning: number;
  connect: (token: string) => void;
  disconnect: () => void;
  sendMessage: (content: string) => void;
}

export function useAgentStream(): UseAgentStreamReturn {
  const [state, setState] = useState<AgentStreamState>({
    events: [],
    status: "idle",
    activeAgents: 0,
    workflowsRunning: 0,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback((token: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    setState((prev) => ({ ...prev, status: "connecting" }));

    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || "wss://api.rasospeak.ai/ws";
    const ws = new WebSocket(`${wsUrl}/${token}`);

    ws.onopen = () => {
      setState((prev) => ({
        ...prev,
        status: "connected",
        activeAgents: (prev.activeAgents || 0) + 1,
      }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        setState((prev) => ({
          ...prev,
          events: [...prev.events, { ...data, timestamp: Date.now() }],
          status:
            data.type === "agent_starting"
              ? "thinking"
              : data.type === "agent_completed"
              ? "connected"
              : prev.status,
        }));
      } catch (e) {
        console.error("Failed to parse WebSocket message:", e);
      }
    };

    ws.onerror = () => {
      setState((prev) => ({ ...prev, status: "error" }));
    };

    ws.onclose = () => {
      setState((prev) => ({
        ...prev,
        status: "idle",
        activeAgents: Math.max(0, (prev.activeAgents || 1) - 1),
      }));

      // Auto-reconnect after 3 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        const storedToken = localStorage.getItem("rasospeak_token");
        if (storedToken) {
          connect(storedToken);
        }
      }, 3000);
    };

    wsRef.current = ws;
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setState((prev) => ({
      ...prev,
      status: "idle",
      events: [],
    }));
  }, []);

  const sendMessage = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "message",
          content,
        })
      );
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    events: state.events,
    status: state.status,
    activeAgents: state.activeAgents,
    workflowsRunning: state.workflowsRunning,
    connect,
    disconnect,
    sendMessage,
  };
}
