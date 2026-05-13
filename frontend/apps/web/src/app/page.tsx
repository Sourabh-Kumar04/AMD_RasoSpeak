"use client";

/**
 * RasoSpeak AI OS — Dashboard Page
 * Production Next.js application with real-time agent visualization
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useAgentStream } from "@/hooks/useAgentStream";
import { useMemory } from "@/hooks/useMemory";
import { AgentVisualizer } from "@/components/agents/AgentVisualizer";
import { MemoryExplorer } from "@/components/memory/MemoryExplorer";
import { StreamingText } from "@/components/chat/StreamingText";
import { ChatInput } from "@/components/chat/ChatInput";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agentId?: string;
  confidence?: number;
}

export default function DashboardPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [tokenBudget, setTokenBudget] = useState({ used: 0, total: 128000 });
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { connect, disconnect, sendMessage, events, status } = useAgentStream();
  const { memories, retrieve, isLoading: memoryLoading } = useMemory();

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Handle incoming events
  useEffect(() => {
    if (events.length === 0) return;

    const latestEvent = events[events.length - 1];

    if (latestEvent.type === "agent_starting") {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          timestamp: new Date(),
          agentId: latestEvent.agentId,
        },
      ]);
    }

    if (latestEvent.type === "token_stream") {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === "assistant") {
          return [
            ...prev.slice(0, -1),
            { ...last, content: last.content + latestEvent.token },
          ];
        }
        return prev;
      });
    }

    if (latestEvent.type === "agent_completed") {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === "assistant") {
          return {
            ...prev.slice(0, -1),
            confidence: latestEvent.confidence,
          } as any;
        }
        return prev;
      });

      setTokenBudget((prev) => ({
        ...prev,
        used: prev.used + (latestEvent.tokens || 0),
      }));
    }

    if (latestEvent.type === "tool_call") {
      console.log("Tool called:", latestEvent.tool);
    }
  }, [events]);

  // Connect WebSocket on mount
  useEffect(() => {
    const token = localStorage.getItem("rasospeak_token");
    if (token) {
      connect(token);
      setIsConnected(true);
    }

    return () => {
      disconnect();
    };
  }, []);

  const handleSendMessage = useCallback(
    async (content: string) => {
      // Add user message
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "user",
          content,
          timestamp: new Date(),
        },
      ]);

      // Send to agent
      sendMessage(content);

      // Retrieve relevant memories in background
      retrieve(content);
    },
    [sendMessage, retrieve]
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center">
              <span className="text-white font-bold text-lg">R</span>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">RasoSpeak</h1>
              <p className="text-xs text-slate-400">AI Operating System</p>
            </div>
          </div>

          <div className="flex items-center gap-6">
            {/* Connection Status */}
            <div className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  isConnected ? "bg-green-500" : "bg-red-500"
                }`}
              />
              <span className="text-sm text-slate-400">
                {isConnected ? "Connected" : "Disconnected"}
              </span>
            </div>

            {/* Token Budget */}
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-xs text-slate-400">Token Budget</p>
                <p className="text-sm text-white font-mono">
                  {(tokenBudget.used / 1000).toFixed(1)}K /{" "}
                  {(tokenBudget.total / 1000).toFixed(0)}K
                </p>
              </div>
              <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-orange-500 to-red-500"
                  style={{
                    width: `${(tokenBudget.used / tokenBudget.total) * 100}%`,
                  }}
                />
              </div>
            </div>

            {/* Memory Usage */}
            <div className="text-right">
              <p className="text-xs text-slate-400">Memories</p>
              <p className="text-sm text-white font-mono">
                {memories.length}
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Chat Area */}
          <div className="lg:col-span-2 space-y-6">
            {/* Chat Messages */}
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 overflow-hidden">
              <div className="p-4 border-b border-slate-700/50">
                <h2 className="text-lg font-semibold text-white">
                  Conversation
                </h2>
              </div>

              <div className="h-[500px] overflow-y-auto p-4 space-y-4">
                {messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center h-full text-slate-500">
                    <div className="w-16 h-16 mb-4 rounded-full bg-slate-700/50 flex items-center justify-center">
                      <svg
                        className="w-8 h-8"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1.5}
                          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                        />
                      </svg>
                    </div>
                    <p className="text-center">
                      Start a conversation with your AI partner
                    </p>
                  </div>
                )}

                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${
                      message.role === "user"
                        ? "justify-end"
                        : "justify-start"
                    }`}
                  >
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                        message.role === "user"
                          ? "bg-gradient-to-r from-orange-600 to-red-600 text-white"
                          : "bg-slate-700/50 text-slate-100"
                      }`}
                    >
                      {message.role === "assistant" ? (
                        <StreamingText text={message.content} />
                      ) : (
                        <p>{message.content}</p>
                      )}
                      <div
                        className={`text-xs mt-1 ${
                          message.role === "user"
                            ? "text-orange-200"
                            : "text-slate-500"
                        }`}
                      >
                        {message.timestamp.toLocaleTimeString()}
                        {message.confidence && (
                          <span className="ml-2">
                            Confidence: {(message.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {/* Agent thinking indicator */}
                {status === "thinking" && (
                  <div className="flex justify-start">
                    <div className="bg-slate-700/50 rounded-2xl px-4 py-3">
                      <div className="flex items-center gap-2 text-slate-400">
                        <div className="flex gap-1">
                          <span className="w-2 h-2 bg-orange-500 rounded-full animate-bounce" />
                          <span
                            className="w-2 h-2 bg-orange-500 rounded-full animate-bounce"
                            style={{ animationDelay: "0.1s" }}
                          />
                          <span
                            className="w-2 h-2 bg-orange-500 rounded-full animate-bounce"
                            style={{ animationDelay: "0.2s" }}
                          />
                        </div>
                        <span className="text-sm">Agent is thinking...</span>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Chat Input */}
              <div className="p-4 border-t border-slate-700/50">
                <ChatInput onSend={handleSendMessage} disabled={!isConnected} />
              </div>
            </div>

            {/* Agent Execution Visualizer */}
            <AgentVisualizer events={events} />
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Memory Explorer */}
            <MemoryExplorer
              memories={memories}
              onRetrieve={retrieve}
              isLoading={memoryLoading}
            />

            {/* Quick Stats */}
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-4">
              <h3 className="text-lg font-semibold text-white mb-4">
                System Status
              </h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Active Agents</span>
                  <span className="text-white font-mono">
                    {status.activeAgents || 0}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Workflows Running</span>
                  <span className="text-white font-mono">
                    {status.workflowsRunning || 0}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Memory Layers</span>
                  <div className="flex gap-1">
                    {["W", "E", "S", "P"].map((layer) => (
                      <div
                        key={layer}
                        className="w-6 h-6 rounded bg-orange-500/20 border border-orange-500/50 flex items-center justify-center text-xs text-orange-400"
                      >
                        {layer}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Provider Status</span>
                  <div className="flex gap-1">
                    <span className="w-2 h-2 rounded-full bg-green-500" />
                    <span className="text-xs text-slate-400 ml-1">
                      Anthropic
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
